import os
import uuid
import asyncio
import threading
import time
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
import webbrowser
import networkx as nx
# 导入我们的RAG模块
from test import RAGWrapper, QueryParam
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['WORKING_DIR'] = './workspace'
app.config['INDICES_FILE'] = './workspace/indices.json'

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['WORKING_DIR'], exist_ok=True)
os.makedirs(os.path.join(app.static_folder, 'visualizations'), exist_ok=True)

# 存储任务状态
tasks = {}
# 存储当前RAG实例
current_rag = None
# 存储索引信息
indices = []
def graphml_to_json(graphml_file):
    G = nx.read_graphml(graphml_file)
    data = nx.node_link_data(G)
    return json.dumps(data)
# 加载已有索引信息
def load_indices():
    global indices
    if os.path.exists(app.config['INDICES_FILE']):
        try:
            with open(app.config['INDICES_FILE'], 'r', encoding='utf-8') as f:
                indices = json.load(f)
        except Exception as e:
            print(f"加载索引信息出错: {str(e)}")
            indices = []
    else:
        indices = []

# 保存索引信息
def save_indices():
    with open(app.config['INDICES_FILE'], 'w', encoding='utf-8') as f:
        json.dump(indices, f, ensure_ascii=False, indent=2)

# 添加新索引
def add_index(name, workspace_dir):
    index_id = str(uuid.uuid4())
    # 使用相对路径存储，避免绝对路径问题
    relative_workspace = os.path.relpath(workspace_dir, os.path.dirname(app.config['INDICES_FILE']))
    index_info = {
        'id': index_id,
        'name': name,
        'workspace_dir': relative_workspace,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    indices.append(index_info)
    save_indices()
    return index_id

# 初始化加载索引
load_indices()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/has_indices')
def has_indices():
    return jsonify({
        'success': True,
        'has_indices': len(indices) > 0
    })

@app.route('/api/indices')
def get_indices():
    return jsonify({
        'success': True,
        'indices': indices
    })

@app.route('/api/use_index/<index_id>')
def use_index(index_id):
    global current_rag
    
    # 查找索引信息
    index_info = next((index for index in indices if index['id'] == index_id), None)
    if not index_info:
        return jsonify({'success': False, 'message': '索引不存在'})
    
    try:
        # 解析工作目录的绝对路径
        if os.path.isabs(index_info['workspace_dir']):
            workspace_dir = index_info['workspace_dir']
        else:
            workspace_dir = os.path.join(os.path.dirname(app.config['INDICES_FILE']), index_info['workspace_dir'])
        
        # 检查工作目录是否存在
        if not os.path.exists(workspace_dir):
            return jsonify({'success': False, 'message': f'索引工作目录不存在: {workspace_dir}'})
        
        # 检查工作目录中是否有必要的索引文件
        required_files = [
            "vdb_entities.json",
            "kv_store_full_docs.json",
            "kv_store_text_chunks.json",
            "graph_chunk_entity_relation.graphml"
        ]
        
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(workspace_dir, f))]
        if missing_files:
            return jsonify({
                'success': False, 
                'message': f'索引文件不完整，缺少: {", ".join(missing_files)}'
            })
        
        # 创建RAG实例
        print(f"使用工作目录: {workspace_dir}")
        current_rag = RAGWrapper(working_dir=workspace_dir)
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        error_msg = f"加载索引出错: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有文件部分'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    if file and file.filename.endswith('.txt'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 为每个上传创建一个唯一的工作目录
        workspace_dir = os.path.join(app.config['WORKING_DIR'], str(uuid.uuid4()))
        os.makedirs(workspace_dir, exist_ok=True)
        
        # 创建任务ID
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            'progress': 0,
            'status': '准备构建索引...',
            'filepath': filepath,
            'workspace_dir': workspace_dir,
            'filename': filename,
            'error': None,
            'index_id': None
        }
        
        # 启动索引构建线程
        threading.Thread(target=build_index, args=(task_id, filepath, workspace_dir, filename)).start()
        
        return jsonify({'success': True, 'task_id': task_id})
    
    return jsonify({'success': False, 'message': '不支持的文件类型'})

@app.route('/api/progress/<task_id>')
def check_progress(task_id):
    if task_id not in tasks:
        return jsonify({'success': False, 'message': '任务不存在'})
    
    return jsonify({
        'progress': tasks[task_id]['progress'],
        'status': tasks[task_id]['status'],
        'error': tasks[task_id]['error'],
        'index_id': tasks[task_id]['index_id']
    })

@app.route('/api/query', methods=['POST'])
def query():
    global current_rag
    
    data = request.json
    question = data.get('question', '')
    index_id = data.get('index_id')
    search_mode = data.get('search_mode', 'global')  # 默认为全局搜索
    
    if not question:
        return jsonify({'success': False, 'message': '问题不能为空'})
    
    if not current_rag:
        return jsonify({'success': False, 'message': '请先上传文档并构建索引或选择已有索引'})
    
    try:
        # 运行异步查询
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        answer = loop.run_until_complete(run_query(question, search_mode))
        loop.close()
        
        return jsonify({'success': True, 'answer': answer})
    except Exception as e:
        import traceback
        error_msg = f"查询出错: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return jsonify({'success': False, 'message': str(e)})

async def run_query(question, search_mode):
    global current_rag
    # 根据搜索模式设置查询参数
    param = QueryParam(mode=search_mode)
    return await current_rag.query(question, param=param)

def build_index(task_id, filepath, workspace_dir, filename):
    global current_rag
    
    try:
        # 更新状态
        tasks[task_id]['status'] = '读取文件...'
        tasks[task_id]['progress'] = 10
        
        # 读取文件内容
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            text = f.read()
        
        tasks[task_id]['status'] = '初始化RAG...'
        tasks[task_id]['progress'] = 20
        
        # 确保工作目录存在
        os.makedirs(workspace_dir, exist_ok=True)
        print(f"创建索引工作目录: {workspace_dir}")
        
        # 创建RAG实例
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 创建RAG实例
        rag = RAGWrapper(working_dir=workspace_dir)
        
        tasks[task_id]['status'] = '构建索引中...'
        tasks[task_id]['progress'] = 30
        
        # 模拟进度更新
        def update_progress():
            for i in range(31, 95):
                if tasks[task_id]['error']:
                    break
                tasks[task_id]['progress'] = i
                time.sleep(0.5)  # 根据实际情况调整
        
        progress_thread = threading.Thread(target=update_progress)
        progress_thread.start()
        
        try:
            # 执行索引构建
            loop.run_until_complete(rag.insert(text))
            
            # 检查索引文件是否已创建
            required_files = [
                "vdb_entities.json",
                "kv_store_full_docs.json",
                "kv_store_text_chunks.json",
                "graph_chunk_entity_relation.graphml"
            ]
            
            missing_files = [f for f in required_files if not os.path.exists(os.path.join(workspace_dir, f))]
            if missing_files:
                raise Exception(f"索引构建完成，但缺少必要的索引文件: {', '.join(missing_files)}")
            
            # 添加索引信息
            index_id = add_index(filename, workspace_dir)
            tasks[task_id]['index_id'] = index_id
            
            # 更新全局RAG实例
            current_rag = rag
            
            # 完成
            tasks[task_id]['status'] = '索引构建完成！'
            tasks[task_id]['progress'] = 100
            print(f"索引构建完成，ID: {index_id}, 工作目录: {workspace_dir}")
        except Exception as e:
            import traceback
            error_msg = f"索引构建过程中出错: {str(e)}\n{traceback.format_exc()}"
            tasks[task_id]['error'] = error_msg
            tasks[task_id]['status'] = f'索引构建失败: {str(e)}'
            print(error_msg)
        finally:
            loop.close()
        
    except Exception as e:
        import traceback
        error_msg = f"索引构建准备阶段出错: {str(e)}\n{traceback.format_exc()}"
        tasks[task_id]['error'] = error_msg
        tasks[task_id]['status'] = f'索引构建失败: {str(e)}'
        print(error_msg)

@app.route('/api/check_indices')
def check_indices():
    results = []
    for index in indices:
        # 解析工作目录的绝对路径
        if os.path.isabs(index['workspace_dir']):
            workspace_dir = index['workspace_dir']
        else:
            workspace_dir = os.path.join(os.path.dirname(app.config['INDICES_FILE']), index['workspace_dir'])
        
        # 检查工作目录是否存在
        dir_exists = os.path.exists(workspace_dir)
        
        # 检查必要的索引文件
        required_files = [
            "vdb_entities.json",
            "kv_store_full_docs.json",
            "kv_store_text_chunks.json",
            "graph_chunk_entity_relation.graphml"
        ]
        
        files_status = {
            f: os.path.exists(os.path.join(workspace_dir, f)) for f in required_files
        }
        
        results.append({
            'id': index['id'],
            'name': index['name'],
            'workspace_dir': workspace_dir,
            'dir_exists': dir_exists,
            'files_status': files_status,
            'created_at': index['created_at']
        })
    
    return jsonify({
        'success': True,
        'indices': results,
        'workspace_base': app.config['WORKING_DIR'],
        'indices_file': app.config['INDICES_FILE']
    })

# 添加可视化路由
@app.route('/api/visualize_graph/<index_id>')
def visualize_graph(index_id):
    global indices
    
    # 查找索引信息
    index_info = next((index for index in indices if index['id'] == index_id), None)
    if not index_info:
        return jsonify({'success': False, 'message': '索引不存在'})
    
    try:
        # 解析工作目录的绝对路径
        if os.path.isabs(index_info['workspace_dir']):
            workspace_dir = index_info['workspace_dir']
        else:
            workspace_dir = os.path.join(os.path.dirname(app.config['INDICES_FILE']), index_info['workspace_dir'])
        
        print(f"工作目录: {workspace_dir}")
        
        # 检查工作目录是否存在
        if not os.path.exists(workspace_dir):
            return jsonify({'success': False, 'message': f'索引工作目录不存在: {workspace_dir}'})
        
        # 检查GraphML文件是否存在
        graphml_file = os.path.join(workspace_dir, "graph_chunk_entity_relation.graphml")
        print(f"GraphML文件路径: {graphml_file}")
        
        if not os.path.exists(graphml_file):
            return jsonify({'success': False, 'message': '知识图谱文件不存在'})
        
        # 创建可视化目录
        vis_dir = os.path.join(app.static_folder, 'visualizations')
        os.makedirs(vis_dir, exist_ok=True)
        print(f"可视化目录: {vis_dir}")
        
        # 生成唯一的HTML文件名
        html_filename = f"graph_{index_id}.html"
        html_path = os.path.join(vis_dir, html_filename)
        print(f"HTML文件路径: {html_path}")
        
        # 生成JSON数据
        json_data = graphml_to_json(graphml_file)
        
        # 创建JSON文件
        json_path = os.path.join(vis_dir, f"graph_json_{index_id}.js")
        print(f"JSON文件路径: {json_path}")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write("var graphJson = " + json_data.replace('\\"', '').replace("'", "\\'").replace("\n", ""))
        
        # 创建HTML文件 - 修改HTML内容以正确引用JS文件
        html_content = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>知识图谱可视化</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body, html {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
        }
        svg {
            width: 100%;
            height: 100%;
        }
        .links line {
            stroke: #999;
            stroke-opacity: 0.6;
        }
        .nodes circle {
            stroke: #fff;
            stroke-width: 1.5px;
        }
        .node-label {
            font-size: 12px;
            pointer-events: none;
        }
        .link-label {
            font-size: 10px;
            fill: #666;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .link:hover .link-label {
            opacity: 1;
        }
        .tooltip {
            position: absolute;
            text-align: left;
            padding: 10px;
            font: 12px sans-serif;
            background: lightsteelblue;
            border: 0px;
            border-radius: 8px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
            max-width: 300px;
        }
        .legend {
            position: absolute;
            top: 10px;
            right: 10px;
            background-color: rgba(255, 255, 255, 0.8);
            padding: 10px;
            border-radius: 5px;
        }
        .legend-item {
            margin: 5px 0;
        }
        .legend-color {
            display: inline-block;
            width: 20px;
            height: 20px;
            margin-right: 5px;
            vertical-align: middle;
        }
    </style>
</head>
<body>
    <svg></svg>
    <div class="tooltip"></div>
    <div class="legend"></div>
    <script type="text/javascript" src="/static/visualizations/graph_json_''' + index_id + '''.js"></script>
    <script>
        const graphData = graphJson;
        
        const svg = d3.select("svg"),
            width = window.innerWidth,
            height = window.innerHeight;

        svg.attr("viewBox", [0, 0, width, height]);

        const g = svg.append("g");

        const entityTypes = [...new Set(graphData.nodes.map(d => d.entity_type))];
        const color = d3.scaleOrdinal(d3.schemeCategory10).domain(entityTypes);

        // 创建图例
        const legend = d3.select(".legend");
        entityTypes.forEach((type, i) => {
            const legendItem = legend.append("div")
                .attr("class", "legend-item");
            
            legendItem.append("div")
                .attr("class", "legend-color")
                .style("background-color", color(type));
            
            legendItem.append("span")
                .text(type);
        });

        const tooltip = d3.select(".tooltip");

        const simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("x", d3.forceX())
            .force("y", d3.forceY());

        const link = g.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(graphData.links)
            .enter().append("line")
            .attr("stroke-width", 1.5);

        const linkLabel = g.append("g")
            .attr("class", "link-labels")
            .selectAll("text")
            .data(graphData.links)
            .enter().append("text")
            .attr("class", "link-label")
            .text(d => d.relation_type || "");

        const node = g.append("g")
            .attr("class", "nodes")
            .selectAll("circle")
            .data(graphData.nodes)
            .enter().append("circle")
            .attr("r", 8)
            .attr("fill", d => color(d.entity_type))
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));

        const nodeLabel = g.append("g")
            .attr("class", "node-labels")
            .selectAll("text")
            .data(graphData.nodes)
            .enter().append("text")
            .attr("class", "node-label")
            .text(d => d.name || d.id);

        node.on("mouseover", function(event, d) {
            tooltip.transition()
                .duration(200)
                .style("opacity", .9);
            
            let tooltipContent = `<strong>ID:</strong> ${d.id}<br>`;
            tooltipContent += `<strong>类型:</strong> ${d.entity_type}<br>`;
            
            if (d.name) {
                tooltipContent += `<strong>名称:</strong> ${d.name}<br>`;
            }
            
            if (d.content) {
                tooltipContent += `<strong>内容:</strong> ${d.content.substring(0, 100)}${d.content.length > 100 ? '...' : ''}<br>`;
            }
            
            tooltip.html(tooltipContent)
                .style("left", (event.pageX + 10) + "px")
                .style("top", (event.pageY - 28) + "px");
        })
        .on("mouseout", function() {
            tooltip.transition()
                .duration(500)
                .style("opacity", 0);
        });

        simulation
            .nodes(graphData.nodes)
            .on("tick", ticked);

        simulation.force("link")
            .links(graphData.links);

        function ticked() {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            linkLabel
                .attr("x", d => (d.source.x + d.target.x) / 2)
                .attr("y", d => (d.source.y + d.target.y) / 2)
                .attr("text-anchor", "middle")
                .attr("dominant-baseline", "middle");

            node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);

            nodeLabel
                .attr("x", d => d.x + 8)
                .attr("y", d => d.y + 3);
        }

        function dragstarted(event) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event) {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }

        const zoom = d3.zoom()
            .scaleExtent([0.1, 10])
            .on("zoom", zoomed);

        svg.call(zoom);

        function zoomed(event) {
            g.attr("transform", event.transform);
        }
    </script>
</body>
</html>
'''
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # 返回可视化URL
        visualization_url = f"/static/visualizations/{html_filename}"
        print(f"可视化URL: {visualization_url}")
        
        return jsonify({'success': True, 'url': visualization_url})
    
    except Exception as e:
        import traceback
        error_msg = f"生成知识图谱可视化出错: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000) 