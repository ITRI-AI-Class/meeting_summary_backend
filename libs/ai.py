from io import BufferedReader
from typing import Optional
from groq import Groq, AsyncGroq
from langchain_groq import ChatGroq
from langchain.document_loaders import PyPDFLoader
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA
import json

class AI:
    # 步驟 1: 載入 PDF 文件並提取內容
    def load_pdf_to_documents(self, pdf_path):
        import os
        if not os.path.exists(pdf_path):
            print("Current working directory:", os.getcwd())
            raise FileNotFoundError(f"File path {pdf_path} is not a valid file or url")
        loader = PyPDFLoader(pdf_path)
        documents = loader.load_and_split()  # 分割為段落
        return documents

    # 步驟 2: 將文檔存儲到 Chroma 向量數據庫
    def create_chroma_vectorstore(self, documents=None):
        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        model_kwargs = {'device': 'cpu'}
        embeddings = HuggingFaceEmbeddings(model_name=model_name,
                                        model_kwargs=model_kwargs)
        # vectorstore = Chroma.from_documents(documents, embeddings, persist_directory="chroma_db")
        # 從已儲存的 chroma_db 加載
        vectorstore = Chroma(persist_directory="chroma_db", embedding_function=embeddings)
        vectorstore.persist()  # 持久化存儲
        return vectorstore

    # 步驟 3: 創建 RAG 應用的檢索器
    def create_retrieval_qa(self, vectorstore):
        retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 3})  # 最相似的 3 條內容
        qa_chain = RetrievalQA.from_chain_type(llm=self.llm, retriever=retriever, return_source_documents=True)
        return qa_chain
    
    def __init__(self, api_key: str, chat_model: str = "deepseek-r1-distill-llama-70b", audio_model: str = "whisper-large-v3", temperature: float = 0):
        self.api_key = api_key
        self.chat_model = chat_model
        self.audio_model = audio_model
        self.temperature = temperature
        self.llm = ChatGroq(
            model=self.chat_model,
            temperature=self.temperature,
            max_retries=2,
            api_key=self.api_key,
        )
        self.client = Groq(api_key=self.api_key)
        
        # 指定 PDF 路徑
        # pdf_path = "rag_data.pdf"  # 替換為你的 PDF 文件路徑

        # 加載 PDF 並創建向量數據庫
        # print("Loading PDF and creating vectorstore...")
        # documents = self.load_pdf_to_documents(pdf_path)
        # vectorstore = self.create_chroma_vectorstore(documents)
        vectorstore = self.create_chroma_vectorstore() 
        # 創建檢索增強生成 (RAG) 的 QA 應用
        print("Creating RetrievalQA...")
        self.qa_chain = self.create_retrieval_qa(vectorstore)
    
    def get_summary(self, text: str) -> dict:
        prompt = """
        角色：
        您是一位專業的文字處理專家，具備細心、耐心、強大的語言能力和豐富的文字處理經驗，並能與不同部門協調合作，確保內容質量與專業性。

        任務：
        請協助總結會議內容，生成會議標籤、會議討論氣氛、會議標題與會議摘要，並以以下格式輸出：
        {
            "tags": [],
            "atmosphere": [],
            "title": "",
            "content": ""
        }

        規則：
        1. 必須逐字閱讀逐字稿，確保沒有遺漏任何關鍵訊息。
        2. 中文用字需淺顯易懂，避免使用晦澀語言。
        3. 提取以下內容：
        - 關鍵討論點
        - 決策內容
        - 行動項目
        - 重要意見
        4. 整理後需確保邏輯清晰、結構連貫。
        5. **摘要需根據輸入內容長度生成相對應的字數：**
        - 100 字的內容，生成 50 字的摘要。
        - 200 字的內容，生成 100 字的摘要。
        - 以此類推，摘要長度需符合內容比例，並涵蓋核心重點。
        6. 摘要需完整且詳細，語言流暢、易於理解。
        7. 僅返回符合 JSON 格式的內容，確保輸出結果無其他額外文字。

        請直接回覆符合上述規範的 JSON 格式。
        """
        
        messages = [
            ("user", text),
            ("user", prompt),
        ]
        output = self.llm.invoke(messages)
        # output = self.qa_chain({"query":messages})
        print(output.content)
        return json.loads(output.content)

    def transcribe_audio(self, file: BufferedReader) -> dict:
        transcription = self.client.audio.transcriptions.create(
            file=file,
            model=self.audio_model,
            response_format="verbose_json",  # Optional
            language="zh",  # Optional
            temperature=self.temperature,  # Optional
        )
        return transcription
    
    def get_chatbot_message(self, message: str) -> dict:
        # output = self.llm.invoke(message)
        output = self.qa_chain.invoke(message)
        # print(output)
        return output['result']
