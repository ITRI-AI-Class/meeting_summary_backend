import argparse
from dotenv import load_dotenv
import firebase_admin
from flask import Flask, render_template, send_from_directory
from flask_cors import CORS
import os
from firebase_admin import credentials

# try:
#     # 设置命令行参数解析器
#     parser = argparse.ArgumentParser(description="Flask application")
#     parser.add_argument('--env', type=str, default='local', choices=['local', 'dev'],
#                         help="Set the environment to 'local' or 'dev'")
#     parser.add_argument('--port', type=int, default=5000, help="Set the port for the Flask server")
#     args = parser.parse_args()

#     # 根据当前环境来设置加载的 .env 文件
#     if args.env == 'local':
#         load_dotenv('.env.local')
#     else:
#         load_dotenv('.env.dev')
# except Exception as e:
#     # print("Error loading .env file")
#     # 使用預設的 .env 文件
#     load_dotenv('.env.dev')

load_dotenv('.env.local')
# load_dotenv('.env.dev')

# 初始化 Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate("./serviceAccount.json")
    firebase_admin.initialize_app(cred)

from controller.openvidu_controller import openvidu_blueprint
from controller.api_controller import api_blueprint
from controller.line_controller import line_blueprint

app = Flask(__name__,static_folder="templates/assets/", template_folder="templates")
CORS(app)

# Register the blueprints with appropriate URL prefixes
app.register_blueprint(api_blueprint, url_prefix='/api')
app.register_blueprint(openvidu_blueprint, url_prefix='/api/openvidu')
app.register_blueprint(line_blueprint, url_prefix='/api/line')  

# 處理前端路由
@app.route('/<path:path>')
def frontend_routes(path):
    try:
        # 嘗試回傳靜態文件（如果存在的話）
        return send_from_directory(app.static_folder, path)
    except:
        # 如果文件不存在，回傳 index.html，交由前端處理
        return render_template('index.html')

# 單一入口路由
@app.route('/')
@app.route('/<path:path>')
def index(path=''):
    return render_template('index.html')

if __name__ == "__main__":
    SERVER_PORT = os.environ.get("SERVER_PORT", 6080)
    # if args.env == 'local':
    #     app.run(debug=True, port=SERVER_PORT)
    # else:
    #     app.run(debug=False, host="0.0.0.0", port=SERVER_PORT, ssl_context=('cert.pem', 'key.pem'))
    app.run(debug=True, port=SERVER_PORT, host="0.0.0.0")
    # app.run(debug=False, host="0.0.0.0", port=SERVER_PORT, ssl_context=('server.crt','server.key'))
