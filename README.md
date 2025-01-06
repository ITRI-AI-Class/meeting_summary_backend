# Meeting Summary Backend

---

## 專案簡介  
Meeting Summary Backend 是一個基於 Python Flask 的後端應用程式，旨在提供高效且可靠的 API 服務，用於生成會議摘要以及會議語音的逐字稿轉換功能。  

---

## 使用技術  
- **Python**: 作為核心開發語言。  
- **Flask**: 提供輕量級的後端框架，用於快速構建 API。   
- **libs.ai 模組**: 自定義模組，負責語音轉錄與摘要生成的邏輯。  

---

## 如何建置專案  

### 1. 安裝必要環境  
確保已安裝以下工具：  
- Python 3.8 或以上版本  
- pip（Python 的套件管理工具）  

### 2. 啟動開發伺服器  
```bash  
python app.py  
```  

### p.s.
若有缺失的lib，請使用pip安裝

---

## 官方文件  
- [Flask 官方文件](https://flask.palletsprojects.com/en/latest/)  
- [Flask-CORS 官方文件](https://flask-cors.readthedocs.io/en/latest/)  
- [Python 官方文件](https://docs.python.org/3/)   

---

## 版本  
v0.0.1  

## 紀錄日期  
2025-01-06  

---

## 功能說明  

### 當前功能  
- **會議摘要生成**：提供會議文本的摘要生成 API，返回結構化的摘要內容。  
- **會議語音轉逐字稿**：將上傳的音訊檔案轉換為逐字稿，並返回時間段對應的文本內容。  

---

## API 範例  

### 1. 生成會議摘要  
**URL**: `/meeting/summarize`  
**方法**: `POST`  
**參數**: 上傳音訊檔案（`audio`）  
**回應格式**:  
```json  
{  
  "message": "success",  
  "data": {  
    "summary": "這是一個摘要範例。",
    "transcription": {
        "duration": 264.64, 
        "segments": [  
          { "id": 1, "startTime": 0, "endTime": 15, "text": "這是一段文字。" },  
          { "id": 2, "startTime": 16, "endTime": 30, "text": "這是另一段文字。" }  
        ]  
    }
  }  
}  
```  

### 2. 錯誤範例  
**回應格式**:  
```json  
{  
  "message": "fail",  
  "error": "No audio file found"  
}  
```  