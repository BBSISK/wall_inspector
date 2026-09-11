from flask import Flask, render_template, jsonify
from config import Config
from models import db, Wall
from routes.admin import admin_bp

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()

        # Seed sample dry-stone wall if table is empty
        if not Wall.query.filter_by(slug="sample-drystone-collapse").first():
            sample_wall = Wall(
                slug="sample-drystone-collapse",
                title="Collapsed Dry Stone Field Boundary",
                description="Traditional dry stone wall showing core collapse and structural bowing.",
                country="United Kingdom",
                region="Yorkshire Dales",
                wall_type="dry_stone",
                structural_function="boundary",
                difficulty="beginner",
                image_filename="drystone_collapse_01.jpg",
                is_published=True
            )
            db.session.add(sample_wall)
            db.session.commit()

    @app.route("/")
    def index():
        walls = Wall.query.filter_by(is_published=True).all()
        return render_template("index.html", walls=[w.to_dict() for w in walls])

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)