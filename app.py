from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from dotenv import load_dotenv
import os
from sqlalchemy.orm import joinedload 


# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configurações do Flask
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurações do Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

db = SQLAlchemy(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Serializador para gerar tokens
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Modelo de Usuário
class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    celular = db.Column(db.String(15), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    reset_token = db.Column(db.String(200), nullable=True)
    token_expira = db.Column(db.DateTime, nullable=True)
    data_registro = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)  # Nova coluna para administrador
    # Campos de endereço
    cep = db.Column(db.String(10), nullable=True)
    logradouro = db.Column(db.String(200), nullable=True)
    numero = db.Column(db.String(10), nullable=True)
    complemento = db.Column(db.String(100), nullable=True)
    bairro = db.Column(db.String(100), nullable=True)
    cidade = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(2), nullable=True)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)
    
class Pedido(db.Model):
    __tablename__ = 'pedido'  # Nome explícito da tabela
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    data_pedido = db.Column(db.DateTime, default=datetime.utcnow)
    local_retirada = db.Column(db.String(50), nullable=False)
    taxa_entrega = db.Column(db.Float, nullable=False, default=0.0)
    total = db.Column(db.Float, nullable=False)
    data_retirada = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='Recebido')
    
    # Relacionamento com Usuário
    usuario = db.relationship('Usuario', backref='pedidos')


# Modelo de ItemPedid
class ItemPedido(db.Model):
    __tablename__ = 'item_pedido'  # Nome explícito da tabela
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False) 
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Float, nullable=False)
    
    # Relacionamentos
    pedido = db.relationship('Pedido', backref=db.backref('itens', lazy='joined'))
    produto = db.relationship('Produto', backref='itens_pedido', lazy='joined')
    
class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(200), nullable=True)
    preco = db.Column(db.Float, nullable=False)
    estoque = db.Column(db.Integer, nullable=False)

# Rotas da interface web


@app.route('/')
def index():
    # Certifique-se que 'estoque' é um campo numérico e a query está correta
    produtos = Produto.query.filter(Produto.estoque > 0).order_by(Produto.nome).all()
    return render_template('index.html', produtos=produtos)
    
@app.route('/admin/pedidos')
@login_required
def pedidos():
    if not current_user.is_admin:  # Verifica se o usuário é administrador
        flash('Acesso negado. Você não é um administrador.', 'erro')
        return redirect(url_for('index'))

    # Buscar todos os pedidos com informações do usuário e itens
    pedidos = Pedido.query.options(
        db.joinedload(Pedido.usuario),
        db.joinedload(Pedido.itens).joinedload(ItemPedido.produto)
    ).order_by(Pedido.data_pedido.desc()).all()
    
    return render_template('pedidos.html', pedidos=pedidos)

@app.route('/')
@login_required
def index2():
    return render_template('index2.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:  # Verifica se o usuário é administrador
        flash('Acesso negado. Você não é um administrador.', 'erro')
        return redirect(url_for('index'))

    # Obter estatísticas ou informações relevantes para o dashboard
    total_usuarios = Usuario.query.count()
    total_produtos = Produto.query.count()
    total_pedidos = Pedido.query.count()
    pedidos_recentes = Pedido.query.order_by(Pedido.data_pedido.desc()).limit(5).all()

    return render_template('admin_dashboard.html', 
                           total_usuarios=total_usuarios, 
                           total_produtos=total_produtos, 
                           total_pedidos=total_pedidos, 
                           pedidos_recentes=pedidos_recentes)

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        is_first_user = Usuario.query.count() == 0
        
        celular = request.form.get('celular')
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        cep = request.form.get('cep')
        logradouro = request.form.get('logradouro')
        numero = request.form.get('numero')
        complemento = request.form.get('complemento')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        estado = request.form.get('estado')

        if not celular or not senha or not email or not cep or not logradouro or not numero or not bairro or not cidade or not estado:
            flash('Todos os campos obrigatórios devem ser preenchidos', 'erro')
            return redirect(url_for('cadastro'))

        if Usuario.query.filter_by(celular=celular).first():
            flash('Número de celular já cadastrado', 'erro')
            return redirect(url_for('cadastro'))

        if Usuario.query.filter_by(email=email).first():
            flash('E-mail já cadastrado', 'erro')
            return redirect(url_for('cadastro'))


        novo_usuario = Usuario(
            
            celular=celular,
            nome=nome,
            email=email,
            cep=cep,
            logradouro=logradouro,
            numero=numero,
            complemento=complemento,
            bairro=bairro,
            cidade=cidade,
            estado=estado
        )
        novo_usuario.definir_senha(senha)
        db.session.add(novo_usuario)
        db.session.commit()

        flash('Cadastro realizado com sucesso!', 'sucesso')
        return redirect(url_for('login'))

    return render_template('cadastro.html')

@app.route('/cadastro_admin', methods=['GET', 'POST'])
def cadastro_admin():
    if request.method == 'POST':
        celular = request.form.get('celular')
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        cep = request.form.get('cep')
        logradouro = request.form.get('logradouro')
        numero = request.form.get('numero')
        complemento = request.form.get('complemento')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        estado = request.form.get('estado')

        novo_usuario = Usuario(
            celular=celular,
            nome=nome,
            email=email,
            cep=cep,
            logradouro=logradouro,
            numero=numero,
            complemento=complemento,
            bairro=bairro,
            cidade=cidade,
            estado=estado,
            is_admin=True  # Definir como administrador
        )
        novo_usuario.definir_senha(senha)
        db.session.add(novo_usuario)
        db.session.commit()

        flash('Administrador cadastrado com sucesso!', 'sucesso')
        return redirect(url_for('index'))

    return render_template('cadastro_admin.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        celular = request.form.get('celular')
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(celular=celular).first()

        if not usuario or not usuario.verificar_senha(senha):
            flash('Número de celular ou senha incorretos', 'erro')
            return redirect(url_for('login'))

        login_user(usuario)
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/recuperar_senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = request.form.get('email')

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario:
            token = serializer.dumps(usuario.email, salt='recuperacao-senha')
            usuario.reset_token = token
            usuario.token_expira = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()

            msg = Message('Recuperação de Senha', recipients=[usuario.email])
            msg.body = f'Para redefinir sua senha, clique no link: {url_for("redefinir_senha", token=token, _external=True)}'
            mail.send(msg)

            flash('Um e-mail com instruções foi enviado para você.', 'sucesso')
            return redirect(url_for('login'))

        flash('E-mail não encontrado.', 'erro')
        return redirect(url_for('recuperar_senha'))

    return render_template('recuperar_senha.html')

@app.route('/redefinir_senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    try:
        email = serializer.loads(token, salt='recuperacao-senha', max_age=3600)
        usuario = Usuario.query.filter_by(email=email).first()

        if not usuario or usuario.reset_token != token or usuario.token_expira < datetime.utcnow():
            flash('Link inválido ou expirado.', 'erro')
            return redirect(url_for('login'))

        if request.method == 'POST':
            nova_senha = request.form.get('nova_senha')
            usuario.definir_senha(nova_senha)
            usuario.reset_token = None
            usuario.token_expira = None
            db.session.commit()

            flash('Senha redefinida com sucesso!', 'sucesso')
            return redirect(url_for('login'))

        return render_template('redefinir_senha.html', token=token)

    except (SignatureExpired, BadSignature):
        flash('Link inválido ou expirado.', 'erro')
        return redirect(url_for('login'))
    
@app.route('/tornar_admin/<int:user_id>')
@login_required
def tornar_admin(user_id):
    if not current_user.is_admin:
        flash('Acesso negado. Você não é um administrador.', 'erro')
        return redirect(url_for('index'))

    usuario = Usuario.query.get(user_id)
    if usuario:
        usuario.is_admin = True
        db.session.commit()
        flash(f'{usuario.nome} foi definido como administrador.', 'sucesso')
    else:
        flash('Usuário não encontrado.', 'erro')

    return redirect(url_for('admin_usuarios'))

@app.route('/atualizar_status/<int:pedido_id>/<status>')
@login_required
def atualizar_status(pedido_id, status):
    if not current_user.is_admin:
        flash('Acesso negado!', 'erro')
        return redirect(url_for('index'))
    
    pedido = Pedido.query.get(pedido_id)
    if pedido:
        pedido.status = status
        db.session.commit()
        flash('Status atualizado!', 'sucesso')
    
    return redirect(url_for('admin_dashboard'))

# Rota para o carrinho de compras
@app.route('/acompanhamento')
@login_required
def acompanhamento():
    pedido = (
        Pedido.query
        .filter_by(usuario_id=current_user.id)
        .options(
            db.joinedload(Pedido.itens).joinedload(ItemPedido.produto)  # Carrega itens e produtos
        )
        .order_by(Pedido.data_pedido.desc())
        .first()
    )
    if not pedido:
        flash('Nenhum pedido encontrado.', 'erro')
        return redirect(url_for('index'))
    return render_template('acompanhamento.html', pedido=pedido)
    
    # Verifica se os itens estão corretamente carregados
    itens_pedido = ItemPedido.query.filter_by(pedido_id=pedido.id).all()
    
    return render_template('acompanhamento.html', pedido=pedido, itens_pedido=itens_pedido)

@app.route('/carrinho', methods=['GET', 'POST'])
@login_required
def carrinho():
    if request.method == 'POST':
        try:
            # Dados básicos do pedido
            local_retirada = request.form.get('local_retirada')
            data_retirada_str = request.form.get('data_retirada')

            # Validação inicial
            if not local_retirada or not data_retirada_str:
                flash('Preencha todos os campos obrigatórios.', 'erro')
                return redirect(url_for('carrinho'))

            data_retirada = datetime.strptime(data_retirada_str, '%Y-%m-%dT%H:%M')

            # Criar pedido
            pedido = Pedido(
                usuario_id=current_user.id,
                local_retirada=local_retirada,
                data_retirada=data_retirada,
                taxa_entrega=10.0 if local_retirada == 'frangolandia' else 0.0,
                total=0.0,
                status='Recebido'
            )
            db.session.add(pedido)
            db.session.flush()  # Gera o ID do pedido sem commit

            total_pedido = 0.0
            itens_validos = False

            # Processar itens do carrinho
            for key in request.form:
                if key.startswith('produto_'):
                    produto_id = int(key.split('_')[1])
                    quantidade = int(request.form.get(key))

                    # Pular quantidades inválidas
                    if quantidade <= 0:
                        continue

                    produto = Produto.query.get(produto_id)
                    if not produto:
                        app.logger.error(f"Produto ID {produto_id} não encontrado")
                        raise ValueError(f"Produto ID {produto_id} não existe")

                    if produto.estoque < quantidade:
                        app.logger.error(f"Estoque insuficiente para {produto.nome} (ID {produto.id})")
                        raise ValueError(f"Estoque insuficiente para {produto.nome}")

                    # Criar item do pedido
                    item = ItemPedido(
                        pedido_id=pedido.id,
                        produto_id=produto.id,
                        quantidade=quantidade,
                        preco_unitario=produto.preco
                    )
                    db.session.add(item)
                    
                    # Atualizar estoque e total
                    produto.estoque -= quantidade
                    total_pedido += produto.preco * quantidade
                    itens_validos = True

                    app.logger.debug(f"Item adicionado: {produto.nome} x{quantidade}")

            # Validar se há itens
            if not itens_validos:
                app.logger.error("Pedido sem itens válidos")
                raise ValueError("Adicione pelo menos um item ao carrinho")

            # Atualizar total do pedido
            pedido.total = total_pedido + pedido.taxa_entrega
            app.logger.debug(f"Total do pedido: {pedido.total}")

            # Commit final
            db.session.commit()
            flash('Pedido confirmado! Aguarde a preparação.', 'sucesso')
            return redirect(url_for('acompanhamento'))

        except ValueError as e:
            db.session.rollback()
            app.logger.error(f"Erro de validação: {str(e)}")
            flash(str(e), 'erro')
            return redirect(url_for('carrinho'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
            flash('Erro interno ao processar o pedido.', 'erro')
            return redirect(url_for('carrinho'))

    # GET: Exibir produtos disponíveis
    produtos = Produto.query.filter(Produto.estoque > 0).all()
    min_date = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
    return render_template('carrinho.html', produtos=produtos, min_date=min_date)


# Rota para o painel do administrador (cadastro de produtos)
@app.route('/admin/produtos', methods=['GET', 'POST'])
@login_required
def admin_produtos():
    if not current_user.is_admin:  # Verifica se o usuário é administrador
        flash('Acesso negado. Você não é um administrador.', 'erro')
        return redirect(url_for('index'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        preco = float(request.form.get('preco'))
        estoque = int(request.form.get('estoque'))

        novo_produto = Produto(
            nome=nome,
            descricao=descricao,
            preco=preco,
            estoque=estoque
        )
        db.session.add(novo_produto)
        db.session.commit()

        flash('Produto cadastrado com sucesso!', 'sucesso')
        return redirect(url_for('admin_produtos'))

    produtos = Produto.query.all()
    return render_template('admin_produtos.html', produtos=produtos)

@app.route('/admin/usuarios')
@login_required
def admin_usuarios():
    if not current_user.is_admin:
        flash('Acesso negado!', 'erro')
        return redirect(url_for('index'))
    
    usuarios = Usuario.query.all()
    return render_template('admin_usuarios.html', usuarios=usuarios)

# Cria o banco de dados e as tabelas
with app.app_context():
    db.create_all()

if __name__ == '__main__':
   app.run(debug=True)
    
   # port = int(os.environ.get("PORT", 8080))
   # app.run(host="0.0.0.0", port=port)