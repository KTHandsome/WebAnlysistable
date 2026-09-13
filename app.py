from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <html>
        <head>
            <title>Phyon Web</title>
        </head>
        <body>
            <h1>Phyon Web</h1>
            <p>Python 3.8.10 + Flask 3.0.3 啟動成功</p>
        </body>
    </html>
    """

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)