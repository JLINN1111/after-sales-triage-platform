from flask import Flask
from app.config import Config


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    @app.get("/")
    def index():
        return "售后报修智能分诊平台项目骨架已就绪"

    return app
