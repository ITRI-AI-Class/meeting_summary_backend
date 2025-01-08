from groq import Groq
from langchain_groq import ChatGroq
import json

api_key = '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'
chat_model = "llama-3.3-70b-specdec"
audio_model = "whisper-large-v3"
temperature = 0

def getSummary(text: str):
    llm = ChatGroq(
        model=chat_model,
        temperature=temperature,
        max_retries=2,
        api_key=api_key,
    )

    messages = [
        ("human", text),
        ("human", "幫我做會議標籤、會議討論的氣氛、會議標題、會議摘要，請以以下json格式輸出{\"tags\":[],\"atmosphere\":[],\"title\":"",\"content\":""}，摘要部分要詳細說明，輸出json即可，其他說明文字不用，要確認是json格式，不要出現不符合規則的字元"),
    ]
    output = llm.invoke(messages)
    return json.loads(output.content)


def transcribeAudio(filename):
    client = Groq(
        api_key=api_key,)

    with open(filename, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(filename, file.read()),
            model=audio_model,
            response_format="verbose_json",  # Optional
            language="zh",  # Optional
            temperature=temperature,  # Optional
        )
        return transcription
