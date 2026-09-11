from flask import Flask, render_template, jsonify
from config import Config
from models import db, Wall

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        walls = Wall.query.filter_by(is_published=True).all()
        return render_template("index.html", walls=[w.to_dict() for w in walls])

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "app": "wall_inspector"})

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)