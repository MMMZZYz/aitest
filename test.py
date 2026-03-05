from google import genai

# 初始化 Client，它会自动读取环境变量 GEMINI_API_KEY
# 也可以显式传入 api_key
client = genai.Client(api_key="AIzaSyCnGm8-xAUcu5QGg2jgNI43mlLWe5LmgK8")

# 使用新版调用方式
response = client.models.generate_content(
    model='gemini-1.5-flash', 
    contents="你好，请做个自我介绍。"
)

print(response.text)