from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from app.config import Config

db = SQLAlchemy()


def create_app(config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    db.init_app(app)

    @app.get("/")
    def index():
        return redirect(url_for("tickets.list_tickets"))

    from app.routes.tickets import tickets_bp
    app.register_blueprint(tickets_bp)

    return app
