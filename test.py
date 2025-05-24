import os
import sys
import logging
import json
import aiohttp
from nano_graphrag.graphrag import GraphRAG
from nano_graphrag.base import QueryParam
from nano_graphrag.base import BaseKVStorage
from nano_graphrag._utils import compute_args_hash, wrap_embedding_func_with_attrs
import numpy as np
sys.path.append("..")
 
logging.basicConfig(level=logging.WARNING)
logging.getLogger("nano-graphrag").setLevel(logging.INFO)
 
# 新的API端点
EMBEDDING_URL = "https://algo-test.ai-indeed.com/ocr/rag/v1/embeddings"
CHAT_URL = "https://algo-test.ai-indeed.com/qwen/rag/v1/chat/completions"
CHAT_MODEL = "qwen-chat"
EMBEDDING_MODEL = "bce-embedding-base"
EMBEDDING_DIM = 768  # 根据bce-embedding-base模型的维度设置，可能需要调整
MAX_TOKEN_SIZE = 8192  # 根据模型的最大token长度设置，可能需要调整

WORKING_DIR = "./workspace"
 
async def model_if_cache(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
 
    # Get the cached response if having-------------------
    hashing_kv: BaseKVStorage = kwargs.pop("hashing_kv", None)
    messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})
    if hashing_kv is not None:
        args_hash = compute_args_hash(CHAT_MODEL, messages)
        if_cache_return = await hashing_kv.get_by_id(args_hash)
        if if_cache_return is not None:
            return if_cache_return["return"]
    # -----------------------------------------------------
    
    # 使用aiohttp调用新的chat API
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": CHAT_MODEL,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 512),
            "temperature": kwargs.get("temperature", 0.7)
        }
        
        async with session.post(CHAT_URL, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"API调用失败: {resp.status}, {error_text}")
            
            response_json = await resp.json()
            content = response_json["choices"][0]["message"]["content"]
    
    # Cache the response if having-------------------
    if hashing_kv is not None:
        await hashing_kv.upsert(
            {args_hash: {"return": content, "model": CHAT_MODEL}}
        )
    # -----------------------------------------------------
    return content
 
 
def remove_if_exist(file):
    if os.path.exists(file):
        os.remove(file)
 
 
def query():
    rag = GraphRAG(
        working_dir=WORKING_DIR,
        best_model_func=model_if_cache,
        cheap_model_func=model_if_cache,
        embedding_func=local_embedding
    )
    print(
        rag.query(
            QUESTION, param=QueryParam(mode="global")
        )
    )
 
 
@wrap_embedding_func_with_attrs(
    embedding_dim=EMBEDDING_DIM,
    max_token_size=MAX_TOKEN_SIZE,
)
async def local_embedding(texts: list[str]) -> np.ndarray:
    # 使用aiohttp调用新的embedding API
    embeddings = []
    async with aiohttp.ClientSession() as session:
        for text in texts:
            payload = {
                "model": EMBEDDING_MODEL,
                "input": text
            }
            
            async with session.post(EMBEDDING_URL, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Embedding API调用失败: {resp.status}, {error_text}")
                
                response_json = await resp.json()
                # 打印API响应以便调试
                print(f"Embedding API响应: {response_json}")
                
                # 根据实际API响应格式获取嵌入向量
                # 可能是 data[0].embedding 或 embedding 或其他格式
                if "data" in response_json and isinstance(response_json["data"], list):
                    embedding = np.array(response_json["data"][0]["embedding"])
                elif "embedding" in response_json:
                    embedding = np.array(response_json["embedding"])
                elif "embeddings" in response_json:
                    embedding = np.array(response_json["embeddings"][0])
                else:
                    # 如果找不到嵌入向量，打印完整响应并抛出异常
                    print(f"无法从响应中提取嵌入向量: {response_json}")
                    raise Exception(f"无法从响应中提取嵌入向量")
                
                embeddings.append(embedding)
    
    return np.array(embeddings)
 
class RAGWrapper:
    def __init__(self, working_dir=WORKING_DIR):
        self.working_dir = working_dir
        self.rag = GraphRAG(
            working_dir=working_dir,
            enable_llm_cache=True,
            best_model_func=model_if_cache,
            cheap_model_func=model_if_cache,
            embedding_func=local_embedding
        )
    
    async def insert(self, text):
        from time import time
        
        start = time()
        # 直接调用异步方法ainsert，而不是insert
        await self.rag.ainsert(text)
        print("indexing time:", time() - start)
        
        return True
    
    async def query(self, question, param=None):
        if param is None:
            param = QueryParam(mode="global")
        
        # 如果有aquery方法，使用它
        if hasattr(self.rag, 'aquery'):
            result = await self.rag.aquery(question, param=param)
        else:
            result = await self.rag.query(question, param=param)
        return result
 
if __name__ == "__main__":
    import asyncio
    
    async def main():
        wrapper = RAGWrapper()
        await wrapper.insert(open(FILEPATH, encoding="utf-8-sig").read())
        result = await wrapper.query(QUESTION)
        print(result)
    
    asyncio.run(main())
