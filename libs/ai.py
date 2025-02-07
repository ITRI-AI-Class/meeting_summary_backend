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
    def create_chroma_vectorstore(self, documents):
        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        model_kwargs = {'device': 'cpu'}
        embeddings = HuggingFaceEmbeddings(model_name=model_name,
                                        model_kwargs=model_kwargs)
        vectorstore = Chroma.from_documents(documents, embeddings, persist_directory="chroma_db")
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
        pdf_path = "rag_data.pdf"  # 替換為你的 PDF 文件路徑

        # 加載 PDF 並創建向量數據庫
        print("Loading PDF and creating vectorstore...")
        documents = self.load_pdf_to_documents(pdf_path)
        vectorstore = self.create_chroma_vectorstore(documents)

        # 創建檢索增強生成 (RAG) 的 QA 應用
        print("Creating RetrievalQA...")
        self.qa_chain = self.create_retrieval_qa(vectorstore)
    
    def get_summary(self, text: str) -> dict:
        prompt = """
        角色:
        您是一個文字處理專家,具備具備高度的細心和耐心,強大的語言能力和豐富的文字處理經驗。校
        對人員必須具備良好的溝通技巧,以便與不同部門協調合作,確保最終出版物的質量和專業性。
        
        任務:
        幫我做會議標籤、會議討論的氣氛、會議標題、會議摘要
        請以以下json格式輸出
        {
            "tags":[],
            "atmosphere":[],
            "title":"",
            "content":""
        }

        規則:
        - 閱讀逐字稿時,一個字都不要漏。
        - 中文用字盡量淺顯、白話。
        - 對每個段落提取關鍵訊息,如關鍵討論點、決策、行動項和意見。
        - 將提取的關鍵訊息進行整理,確保邏輯順序和連貫性。
        - 將總結的段落或列表進行潤飾,確保語言流暢且易於理解。
        - 摘要部分要詳細說明，輸出json即可，其他說明文字不用，要確認是json格式，不要出現不符合規則的字元
        """
        
        messages = [
            ("user", text),
            ("user", prompt),
        ]
        output = self.llm.invoke(messages)
        # output = self.qa_chain({"query":messages})
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
    
    def get_chatbot_message(self, message: list) -> dict:
        output = self.llm.invoke(message)
        # output = self.qa_chain.invoke(message)
        # print(output)
        return output.content
