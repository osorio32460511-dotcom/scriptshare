import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, Response, abort
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
from pygments.formatters import HtmlFormatter
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Database config
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Paste(db.Model):
    id = db.Column(db.String(8), primary_key=True)
    title = db.Column(db.String(200))
    content = db.Column(db.Text)  # Para código
    language = db.Column(db.String(50))
    type = db.Column(db.String(10))  # 'code' ou 'file'
    filename = db.Column(db.String(255))
    mime_type = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    file_data = db.Column(db.LargeBinary)  # Arquivos salvos no banco
    
    def get_size(self):
        if self.file_data:
            return len(self.file_data)
        return 0

# Cria tabelas
with app.app_context():
    db.create_all()

def generate_id():
    return str(uuid.uuid4())[:8]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' in request.files and request.files['file'].filename:
        # Upload de arquivo
        file = request.files['file']
        file_id = generate_id()
        file_content = file.read()
        
        paste = Paste(
            id=file_id,
            title=request.form.get('title') or file.filename,
            type='file',
            filename=secure_filename(file.filename),
            mime_type=file.mimetype or 'application/octet-stream',
            file_data=file_content
        )
        
        db.session.add(paste)
        db.session.commit()
        
        return {'success': True, 'url': f"{request.host_url}{file_id}", 'id': file_id}
    
    elif request.form.get('code'):
        # Paste de código
        code_id = generate_id()
        language = request.form.get('language', 'text')
        
        paste = Paste(
            id=code_id,
            title=request.form.get('title') or 'Snippet sem título',
            content=request.form.get('code'),
            language=language,
            type='code'
        )
        
        db.session.add(paste)
        db.session.commit()
        
        return {'success': True, 'url': f"{request.host_url}{code_id}", 'id': code_id}
    
    return {'success': False, 'error': 'Nenhum conteúdo enviado'}, 400

@app.route('/<id>')
def view(id):
    paste = Paste.query.get_or_404(id)
    paste.views += 1
    db.session.commit()
    
    if paste.type == 'code':
        try:
            if paste.language == 'auto':
                lexer = guess_lexer(paste.content)
            else:
                lexer = get_lexer_by_name(paste.language)
        except:
            lexer = TextLexer()
        
        formatter = HtmlFormatter(style='monokai', linenos=True, cssclass='highlight')
        highlighted = highlight(paste.content, lexer, formatter)
        css = formatter.get_style_defs()
        
        return render_template('view_code.html', paste=paste, highlighted=highlighted, css=css)
    else:
        return render_template('view_file.html', paste=paste)

@app.route('/raw/<id>')
def raw(id):
    paste = Paste.query.get_or_404(id)
    
    if paste.type == 'code':
        return Response(paste.content, mimetype='text/plain')
    else:
        if not paste.file_data:
            abort(404)
        return Response(
            paste.file_data,
            mimetype=paste.mime_type,
            headers={'Content-Disposition': f'attachment; filename="{paste.filename}"'}
        )

@app.route('/download/<id>')
def download(id):
    paste = Paste.query.get_or_404(id)
    if not paste.file_data:
        abort(404)
    return Response(
        paste.file_data,
        mimetype=paste.mime_type,
        headers={'Content-Disposition': f'attachment; filename="{paste.filename}"'}
    )

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
