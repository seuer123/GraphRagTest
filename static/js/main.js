document.addEventListener('DOMContentLoaded', function() {
    // DOM元素
    const newIndexBtn = document.getElementById('newIndexBtn');
    const existingIndexBtn = document.getElementById('existingIndexBtn');
    const uploadSection = document.querySelector('.upload-section');
    const existingIndexSection = document.querySelector('.existing-index-section');
    const fileInput = document.getElementById('fileInput');
    const fileName = document.getElementById('fileName');
    const uploadBtn = document.getElementById('uploadBtn');
    const progressSection = document.querySelector('.progress-section');
    const progressBar = document.getElementById('progressBar');
    const progressStatus = document.getElementById('progressStatus');
    const querySection = document.querySelector('.query-section');
    const currentIndexName = document.getElementById('currentIndexName');
    const questionInput = document.getElementById('questionInput');
    const askBtn = document.getElementById('askBtn');
    const answerContent = document.getElementById('answerContent');
    const indexList = document.getElementById('indexList');
    const visualizeBtn = document.getElementById('visualizeBtn');
    
    let uploadedFile = null;
    let currentIndex = null;
    
    // 模式切换
    newIndexBtn.addEventListener('click', function() {
        newIndexBtn.classList.add('active');
        existingIndexBtn.classList.remove('active');
        uploadSection.style.display = 'block';
        existingIndexSection.style.display = 'none';
    });
    
    existingIndexBtn.addEventListener('click', function() {
        existingIndexBtn.classList.add('active');
        newIndexBtn.classList.remove('active');
        uploadSection.style.display = 'none';
        existingIndexSection.style.display = 'block';
        
        // 加载已有索引列表
        loadExistingIndices();
    });
    
    // 加载已有索引
    function loadExistingIndices() {
        indexList.innerHTML = '<p class="loading">正在加载已有索引...</p>';
        
        fetch('/api/indices')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.indices.length > 0) {
                let html = '';
                data.indices.forEach(index => {
                    html += `
                    <div class="index-item" data-id="${index.id}">
                        <div class="index-info">
                            <div class="index-name">${index.name}</div>
                            <div class="index-date">创建时间: ${index.created_at}</div>
                        </div>
                        <div class="index-actions">
                            <button class="use-index-btn"><i class="fas fa-check-circle"></i> 使用此索引</button>
                        </div>
                    </div>
                    `;
                });
                indexList.innerHTML = html;
                
                // 添加使用索引按钮事件
                document.querySelectorAll('.use-index-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        const indexItem = this.closest('.index-item');
                        const indexId = indexItem.dataset.id;
                        const indexName = indexItem.querySelector('.index-name').textContent;
                        
                        useExistingIndex(indexId, indexName);
                    });
                });
            } else {
                indexList.innerHTML = '<p class="placeholder">没有找到已有索引，请先创建新索引。</p>';
            }
        })
        .catch(error => {
            indexList.innerHTML = `<p class="error">加载索引失败: ${error.message}</p>`;
        });
    }
    
    // 使用已有索引
    function useExistingIndex(indexId, indexName) {
        fetch(`/api/use_index/${indexId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                currentIndex = {
                    id: indexId,
                    name: indexName
                };
                currentIndexName.textContent = indexName;
                
                // 启用可视化按钮
                visualizeBtn.disabled = false;
                
                // 显示问答区域
                querySection.style.display = 'block';
                
                // 滚动到问答区域
                querySection.scrollIntoView({ behavior: 'smooth' });
            } else {
                alert(`无法使用此索引: ${data.message}`);
            }
        })
        .catch(error => {
            alert(`请求出错: ${error.message}`);
        });
    }
    
    // 文件选择事件
    fileInput.addEventListener('change', function(e) {
        if (this.files.length > 0) {
            uploadedFile = this.files[0];
            fileName.textContent = uploadedFile.name;
            uploadBtn.disabled = false;
        } else {
            fileName.textContent = '未选择文件';
            uploadBtn.disabled = true;
        }
    });
    
    // 上传并构建索引
    uploadBtn.addEventListener('click', function() {
        if (!uploadedFile) return;
        
        const formData = new FormData();
        formData.append('file', uploadedFile);
        
        // 显示进度区域
        progressSection.style.display = 'block';
        uploadBtn.disabled = true;
        
        // 发送上传请求
        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('上传失败');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // 开始轮询索引构建进度
                checkIndexingProgress(data.task_id, uploadedFile.name);
            } else {
                progressStatus.textContent = '上传失败: ' + data.message;
                uploadBtn.disabled = false;
            }
        })
        .catch(error => {
            progressStatus.textContent = '上传出错: ' + error.message;
            uploadBtn.disabled = false;
        });
    });
    
    // 检查索引构建进度
    function checkIndexingProgress(taskId, filename) {
        const progressCheck = setInterval(() => {
            fetch(`/api/progress/${taskId}`)
            .then(response => response.json())
            .then(data => {
                // 更新进度条
                progressBar.style.width = `${data.progress}%`;
                progressStatus.textContent = data.status;
                
                // 如果完成
                if (data.progress === 100) {
                    clearInterval(progressCheck);
                    progressStatus.textContent = '索引构建完成！';
                    
                    // 更新当前索引信息
                    currentIndex = {
                        id: data.index_id,
                        name: filename
                    };
                    currentIndexName.textContent = filename;
                    
                    // 启用可视化按钮
                    visualizeBtn.disabled = false;
                    
                    // 显示问答区域
                    setTimeout(() => {
                        querySection.style.display = 'block';
                        
                        // 滚动到问答区域
                        querySection.scrollIntoView({ behavior: 'smooth' });
                    }, 1000);
                }
                
                // 如果出错
                if (data.error) {
                    clearInterval(progressCheck);
                    progressStatus.textContent = '索引构建失败: ' + data.error;
                    uploadBtn.disabled = false;
                }
            })
            .catch(error => {
                clearInterval(progressCheck);
                progressStatus.textContent = '检查进度出错: ' + error.message;
                uploadBtn.disabled = false;
            });
        }, 1000); // 每秒检查一次
    }
    
    // 提问问题
    askBtn.addEventListener('click', function() {
        const question = questionInput.value.trim();
        if (!question) return;
        
        // 获取选中的搜索模式
        const searchMode = document.querySelector('input[name="searchMode"]:checked').value;
        
        // 显示加载状态
        answerContent.innerHTML = '<p class="loading">正在思考中...</p>';
        askBtn.disabled = true;
        
        // 发送问题
        fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                question: question,
                index_id: currentIndex ? currentIndex.id : null,
                search_mode: searchMode
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 显示回答
                answerContent.innerHTML = `<p>${data.answer.replace(/\n/g, '<br>')}</p>`;
            } else {
                answerContent.innerHTML = `<p class="error">获取回答失败: ${data.message}</p>`;
            }
            askBtn.disabled = false;
        })
        .catch(error => {
            answerContent.innerHTML = `<p class="error">请求出错: ${error.message}</p>`;
            askBtn.disabled = false;
        });
    });
    
    // 添加搜索模式选择的样式效果
    document.querySelectorAll('.search-mode-option').forEach(option => {
        option.addEventListener('click', function() {
            const radio = this.querySelector('input[type="radio"]');
            radio.checked = true;
            
            // 更新样式
            document.querySelectorAll('.search-mode-option').forEach(opt => {
                if (opt.querySelector('input[type="radio"]').checked) {
                    opt.style.borderColor = '#3498db';
                    opt.style.boxShadow = '0 0 0 2px rgba(52, 152, 219, 0.2)';
                } else {
                    opt.style.borderColor = '#e0e0e0';
                    opt.style.boxShadow = 'none';
                }
            });
        });
    });
    
    // 初始化搜索模式样式
    document.querySelectorAll('.search-mode-option').forEach(option => {
        const radio = option.querySelector('input[type="radio"]');
        if (radio.checked) {
            option.style.borderColor = '#3498db';
            option.style.boxShadow = '0 0 0 2px rgba(52, 152, 219, 0.2)';
        }
    });
    
    // 检查是否有已有索引
    fetch('/api/has_indices')
    .then(response => response.json())
    .then(data => {
        if (data.success && data.has_indices) {
            // 自动点击"使用已有索引"按钮
            existingIndexBtn.click();
        }
    })
    .catch(error => {
        console.error('检查索引状态出错:', error);
    });

    // 添加搜索模式帮助按钮
    const searchModeTitle = document.querySelector('.search-mode p');
    const helpIcon = document.createElement('i');
    helpIcon.className = 'fas fa-question-circle help-icon';
    helpIcon.style.marginLeft = '5px';
    helpIcon.style.cursor = 'pointer';
    helpIcon.style.color = '#3498db';
    searchModeTitle.appendChild(helpIcon);

    // 添加帮助提示
    helpIcon.addEventListener('click', function() {
        const helpText = `
            <div class="help-modal">
                <div class="help-content">
                    <h3>搜索模式说明</h3>
                    <div class="mode-help">
                        <h4><i class="fas fa-globe"></i> 全局搜索</h4>
                        <p>全局搜索会考虑整个文档的内容，适合回答以下类型的问题：</p>
                        <ul>
                            <li>概括整个文档的主题</li>
                            <li>分析文档的整体结构</li>
                            <li>提取文档的主要观点</li>
                            <li>需要综合多处信息的问题</li>
                        </ul>
                    </div>
                    <div class="mode-help">
                        <h4><i class="fas fa-search"></i> 局部搜索</h4>
                        <p>局部搜索会专注于与问题最相关的文档片段，适合回答以下类型的问题：</p>
                        <ul>
                            <li>查找特定事实或数据</li>
                            <li>询问具体细节</li>
                            <li>引用特定段落或句子</li>
                            <li>需要精确定位信息的问题</li>
                        </ul>
                    </div>
                    <button class="close-help">关闭</button>
                </div>
            </div>
        `;
        
        const helpModal = document.createElement('div');
        helpModal.innerHTML = helpText;
        document.body.appendChild(helpModal);
        
        // 添加样式
        const style = document.createElement('style');
        style.textContent = `
            .help-modal {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.5);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 1000;
            }
            .help-content {
                background-color: white;
                border-radius: 12px;
                padding: 30px;
                max-width: 600px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
            }
            .help-content h3 {
                margin-top: 0;
                color: #2c3e50;
                border-bottom: 2px solid #3498db;
                padding-bottom: 10px;
            }
            .mode-help {
                margin-bottom: 20px;
            }
            .mode-help h4 {
                color: #3498db;
                margin-bottom: 10px;
            }
            .mode-help ul {
                padding-left: 20px;
            }
            .mode-help li {
                margin-bottom: 5px;
            }
            .close-help {
                background: linear-gradient(to right, #3498db, #2980b9);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 30px;
                cursor: pointer;
                margin-top: 20px;
                transition: all 0.3s;
            }
            .close-help:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 10px rgba(52, 152, 219, 0.3);
            }
        `;
        document.head.appendChild(style);
        
        // 关闭按钮事件
        document.querySelector('.close-help').addEventListener('click', function() {
            helpModal.remove();
            style.remove();
        });
    });

    // 添加知识图谱可视化按钮事件
    visualizeBtn.addEventListener('click', function() {
        if (!currentIndex) {
            alert('请先选择或创建索引');
            return;
        }
        
        visualizeBtn.disabled = true;
        visualizeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
        
        fetch(`/api/visualize_graph/${currentIndex.id}`)
        .then(response => response.json())
        .then(data => {
            visualizeBtn.disabled = false;
            visualizeBtn.innerHTML = '<i class="fas fa-project-diagram"></i> 查看知识图谱';
            
            if (data.success) {
                console.log('可视化URL:', data.url);
                // 在新窗口打开可视化页面
                window.open(data.url, '_blank');
            } else {
                console.error('可视化失败:', data.message);
                alert(`生成知识图谱失败: ${data.message}`);
            }
        })
        .catch(error => {
            console.error('可视化请求错误:', error);
            visualizeBtn.disabled = false;
            visualizeBtn.innerHTML = '<i class="fas fa-project-diagram"></i> 查看知识图谱';
            alert(`请求出错: ${error.message}`);
        });
    });

    // 初始化时禁用可视化按钮
    visualizeBtn.disabled = true;
});

// 添加调试功能
function addDebugButton() {
    const container = document.querySelector('.container');
    const debugBtn = document.createElement('button');
    debugBtn.textContent = '检查索引状态';
    debugBtn.style.marginTop = '20px';
    debugBtn.style.backgroundColor = '#e74c3c';
    
    debugBtn.addEventListener('click', function() {
        fetch('/api/check_indices')
        .then(response => response.json())
        .then(data => {
            console.log('索引状态:', data);
            alert('索引状态已在控制台输出，请按F12查看');
            
            // 创建一个简单的状态显示
            let status = '索引状态:\n\n';
            data.indices.forEach(index => {
                status += `ID: ${index.id}\n`;
                status += `名称: ${index.name}\n`;
                status += `工作目录: ${index.workspace_dir}\n`;
                status += `目录存在: ${index.dir_exists ? '是' : '否'}\n`;
                status += `文件状态:\n`;
                for (const [file, exists] of Object.entries(index.files_status)) {
                    status += `  - ${file}: ${exists ? '存在' : '缺失'}\n`;
                }
                status += `创建时间: ${index.created_at}\n\n`;
            });
            
            status += `工作目录基础路径: ${data.workspace_base}\n`;
            status += `索引文件: ${data.indices_file}\n`;
            
            const debugOutput = document.createElement('pre');
            debugOutput.style.backgroundColor = '#f8f9fa';
            debugOutput.style.padding = '15px';
            debugOutput.style.borderRadius = '8px';
            debugOutput.style.marginTop = '20px';
            debugOutput.style.whiteSpace = 'pre-wrap';
            debugOutput.style.fontSize = '14px';
            debugOutput.style.fontFamily = 'monospace';
            debugOutput.textContent = status;
            
            // 如果已有输出，则替换
            const existingOutput = document.getElementById('debugOutput');
            if (existingOutput) {
                existingOutput.remove();
            }
            
            debugOutput.id = 'debugOutput';
            container.appendChild(debugOutput);
        })
        .catch(error => {
            console.error('检查索引状态出错:', error);
            alert('检查索引状态出错: ' + error.message);
        });
    });
    
    container.appendChild(debugBtn);
}

// 在页面加载完成后添加调试按钮
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    addDebugButton();
} 