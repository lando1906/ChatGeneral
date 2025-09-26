import os
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

# --- App Configuration ---
app = Flask(__name__, template_folder='templates', static_folder='static')

# Use environment variable for secret key in production for security
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# --- Database Configuration ---
# Set the base directory for the app
basedir = os.path.abspath(os.path.dirname(__file__))
# Configure the database URI for SQLite. Render uses a persistent disk at /var/data
db_path = os.path.join(os.environ.get('RENDER_DISK_PATH', basedir), 'toduslinks.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

# --- Database Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=False)
    post_type = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'link': self.link,
            'description': self.description,
            'image': self.image,
            'type': self.post_type,
            'author': self.author.username,
            'timestamp': self.timestamp.isoformat()
        }

# --- Main Route ---
@app.route('/')
def index():
    # The main HTML file is rendered from the templates folder
    return render_template('index.html')

# --- API Routes ---

# User Authentication
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400

    if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
        return jsonify({'status': 'error', 'message': 'User already exists'}), 409

    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    
    session['user_id'] = new_user.id
    session['username'] = new_user.username
    return jsonify({'status': 'success', 'message': 'User created successfully', 'username': new_user.username})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if user and user.check_password(password):
        session['user_id'] = user.id
        session['username'] = user.username
        return jsonify({'status': 'success', 'message': 'Logged in successfully', 'username': user.username})
    
    return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'success', 'message': 'Logged out successfully'})

@app.route('/api/session', methods=['GET'])
def check_session():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'username': session.get('username')})
    return jsonify({'logged_in': False})

# Posts
@app.route('/api/posts', methods=['GET'])
def get_posts():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    return jsonify([post.to_dict() for post in posts])

@app.route('/api/posts', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.get_json()
    link = data.get('link')
    description = data.get('description')
    image = data.get('image')
    post_type = data.get('type')

    if not all([link, description, image, post_type]):
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400

    new_post = Post(
        link=link,
        description=description,
        image=image,
        post_type=post_type,
        user_id=session['user_id']
    )
    db.session.add(new_post)
    db.session.commit()
    
    # Notify all connected clients about the new post
    socketio.emit('new_post', new_post.to_dict())
    
    return jsonify({'status': 'success', 'message': 'Post created', 'post': new_post.to_dict()}), 201

# --- Utility to create tables ---
def init_db():
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Database tables created.")
        
        # Optional: Create a default user and a few posts if the DB is empty
        if not User.query.first():
            print("Creating default data...")
            default_user = User(username='admin', email='admin@todus.links')
            default_user.set_password('admin')
            db.session.add(default_user)
            db.session.commit()

            posts_data = [
                 {
                    'link': "#", 'description': "Canal oficial de noticias y actualizaciones de la comunidad de desarrolladores de Cuba. ¡Únete para estar al día!",
                    # CORREGIDO: Se cambiaron las comillas invertidas por comillas dobles
                    'image': "https://placehold.co/100x100/1f2937/9ca3af?text=DevCU", 'post_type': "Canal", 'user_id': default_user.id
                },
                {
                    'link': "#", 'description': "Grupo para los amantes de la fotografía. Comparte tus mejores capturas, aprende nuevas técnicas y participa en retos.",
                    # CORREGIDO: Se cambiaron las comillas invertidas por comillas dobles
                    'image': "https://placehold.co/100x100/1f2937/9ca3af?text=Foto", 'post_type': "Grupo", 'user_id': default_user.id
                },
            ]
            for p in posts_data:
                post = Post(**p)
                db.session.add(post)
            db.session.commit()
            print("Default data created.")

if __name__ == '__main__':
    # This is for local development
    # To initialize the database, run in your terminal:
    # python -c "from app import init_db; init_db()"
    socketio.run(app, debug=True)