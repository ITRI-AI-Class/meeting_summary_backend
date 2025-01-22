from io import BufferedReader
from typing import Optional
from groq import Groq, AsyncGroq
from langchain_groq import ChatGroq
import json

class AI:
    def __init__(self, api_key: str, chat_model: str = "llama-3.3-70b-specdec", audio_model: str = "whisper-large-v3", temperature: float = 0):
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

    def get_summary(self, text: str) -> dict:
        messages = [
            ("human", text),
            ("human", "幫我做會議標籤、會議討論的氣氛、會議標題、會議摘要，請以以下json格式輸出{\"tags\":[],\"atmosphere\":[],\"title\":\"\",\"content\":\"\"}，摘要部分要詳細說明，輸出json即可，其他說明文字不用，要確認是json格式，不要出現不符合規則的字元"),
        ]
        output = self.llm.invoke(messages)
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
