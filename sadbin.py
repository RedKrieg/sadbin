#!/usr/bin/env python

from hashlib import sha1
from flask.ext.bootstrap import Bootstrap
from flask.ext.redis import Redis
from flask.ext.login import LoginManager, UserMixin
from flask.ext.login import login_user, login_required
from flask.ext.login import logout_user, current_user
from flask.ext.wtf import Form
from flask.ext.wtf import RecaptchaField
from wtforms import PasswordField, TextField, TextAreaField, SelectField
from wtforms.validators import Length, InputRequired, NumberRange
from wtforms.validators import Email, EqualTo
from werkzeug.security import check_password_hash, generate_password_hash
from pygments import highlight
from pygments.lexers import guess_lexer, get_lexer_by_name, get_all_lexers
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from humanize import naturalday, naturaltime
from flask.ext.sqlalchemy import SQLAlchemy
import flask, datetime

# The next three lines of horror are to work around everything in Python2 being
# non-unicode by default and jinja2 choking because of it.
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

app = flask.Flask(__name__)
app.config.from_pyfile(u'instance/application.cfg')

# Flask-And-Redis
redis = Redis(app)

# Flask-Bootstrap
Bootstrap(app)

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# Flask-SQLAlchemy
db = SQLAlchemy(app)

# Defaults
if 'MAX_UPLOAD_SIZE' not in app.config:
    app.config['MAX_UPLOAD_SIZE'] = 2**18
if 'DEFAULT_EXPIRE_TIME' not in app.config:
    app.config['DEFAULT_EXPIRE_TIME'] = 3600 * 365
if 'MAX_TITLE_LENGTH' not in app.config:
    app.config['MAX_TITLE_LENGTH'] = 256
if 'MAX_AUTHOR_LENGTH' not in app.config:
    app.config['MAX_AUTHOR_LENGTH'] = 256
if 'MAX_LOGIN_LENGTH' not in app.config:
    app.config['MAX_LOGIN_LENGTH'] = 256
if 'MAX_PASSWORD_LENGTH' not in app.config:
    app.config['MAX_PASSWORD_LENGTH'] = 256

def get_lexer_list():
    """Iterator which yields the first lexer short-name and the lexer long
    name as a two-tuple."""
    yield ('none',"Guess Language")
    for lexer in sorted(get_all_lexers(), key=lambda x: x[0].lower()):
        yield lexer[1][0], lexer[0]

def get_duration_list():
    """Iterator which yields a list of durations with numeric value and long
    name as a two-tuple."""
    now = datetime.datetime.now() + datetime.timedelta(seconds = 30)
    for seconds in [ 5*60, 15*60, 30*60, 3600, 2*3600, 4*3600, 6*3600, 12*3600,
                    24*3600, 48*3600, 7*24*3600, 14*24*3600, 30*24*3600,
                    90*24*3600, 365*24*3600 ]:
        yield (
            u'%d' % seconds,
            naturaltime(now + datetime.timedelta(seconds=seconds)).capitalize()
        )
    yield (u'-1', "Never")

# Forms
class Paste(Form):
    title = TextField(
        u'Title:',
        [
            Length(
                max = app.config['MAX_TITLE_LENGTH'],
                message = u"Max title length is %d" % (
                    app.config['MAX_TITLE_LENGTH']
                )
            )
        ]
    )
    author = TextField(
        u'Author:',
        [
            Length(
                max = app.config['MAX_AUTHOR_LENGTH'],
                message = u"Max author length is %d" % (
                    app.config['MAX_AUTHOR_LENGTH']
                )
            )
        ]
    )
    language = SelectField(
        u'Language:',
        choices = [ i for i in get_lexer_list() ]
    )
    expire_time = SelectField(
        u'Expires:',
        choices = [ i for i in get_duration_list() ]
    )
    paste_content = TextAreaField(
        u'Paste Data:',
        [
            Length(
                max = app.config['MAX_UPLOAD_SIZE'],
                message = u"Max upload size is %dKiB" % (
                    app.config['MAX_UPLOAD_SIZE'] / 1024
                )
            ),
            InputRequired(
                message = u"You must enter data."
            )
        ]
    )

class CaptchaPaste(Paste):
    captcha = RecaptchaField(
        u'Recaptcha:'
    )

class LoginForm(Form):
    email = TextField(
        u'Email:',
        [   
            Length( 
                max = app.config['MAX_LOGIN_LENGTH'], 
                message = u"Max login length is %d" % (
                    app.config['MAX_LOGIN_LENGTH']
                )
            ),
            InputRequired(
                message = u"You must enter a user name."
            ),
            Email(
                message = u"Not a valid email address."
            )
        ]
    )
    password = PasswordField(
        u'Password:',
        [
            Length(
                max = app.config['MAX_PASSWORD_LENGTH'],
                message = u"Max password length is %d" % (
                    app.config['MAX_PASSWORD_LENGTH']
                )
            ),
            InputRequired(
                message = u"You must enter a password."
            )
        ]
    )

class RegisterForm(LoginForm):
    password2 = PasswordField(
        u'Password (again):',
        [
            Length(
                max = app.config['MAX_PASSWORD_LENGTH'],
                message = u"Max password length is %d" % (
                    app.config['MAX_PASSWORD_LENGTH']
                )
            ),
            InputRequired(
                message = u"You must enter a password."
            ),
            EqualTo(
                "password",
                message = u"Passwords must match."
            )
        ]
    )
    captcha = RecaptchaField(
        u'Recaptcha:'
    )


# User object
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    auth_hash = db.Column(db.String(256))
    active = db.Column(db.Boolean())
    def __init__(self, email, auth_hash, active=True):
        self.email = email
        self.active = active
        self.auth_hash = auth_hash
    def __repr__(self):
        return '<User %r>' % self.email
    def get_id(self):
        return unicode(self.id)
    def is_active(self, set_active = None):
        if set_active is not None:
            self.active = set_active
        return self.active
    def is_anonymous(self):
        return False
    def is_authenticated(self):
        return True

def save_paste(key, paste_data,
               language = u'none', title = u'', author = u'',
               expire_in = None):
    if not expire_in:
        expire_in = app.config['DEFAULT_EXPIRE_TIME']
    data = {
        'paste_content': paste_data,
        'language': language,
        'title': title,
        'author': author
    }
    redis.hmset(key, data)
    if expire_in >= 0:
        redis.expire(key, expire_in)

def highlight_content(content, lexer_name = None):
    if not lexer_name:
        lexer = guess_lexer(content)
    else:
        try:
            lexer = get_lexer_by_name(lexer_name)
        except ClassNotFound:
            lexer = guess_lexer(content)
    formatter = HtmlFormatter()
    return highlight(content.decode('utf8'), lexer, formatter)

def fill_form_from_db(key, form):
    """Fills a form from the database, sets expire_time to the first duration
    larger than the current TTL."""
    try:
        data = redis.hgetall(key)
    except:
        data = {}
    for field in [ i.name for i in form ]:
        try:
            form[field].data = data[field]
        except:
            pass # Leave default values
    ttl = redis.ttl(key)
    expire_list = [ int(i[0]) for i in form.expire_time.choices if i[0]!='-1']
    for expire_time in reversed(expire_list):
        if ttl <= expire_time:
            form.expire_time.data = u'%d' % expire_time

@login_manager.user_loader
def load_user(user_id):
    return User.query.filter_by(id=user_id).first()

@app.route('/register/', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        db.create_all()
        password = form.password.data
        email = form.email.data
        auth_hash = generate_password_hash(password)
        try:
            new_user = User(email, auth_hash)
            db.session.add(new_user)
            db.session.commit()
        except:
            form.email.errors.append("Address is already registered!")
            return flask.render_template("login.html", form=form)
        return flask.redirect(
            flask.request.args.get("next") or
            flask.url_for("login")
        )
    return flask.render_template("login.html", form=form)

@app.route("/login/", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # login and validate the user...
        user = User.query.filter_by(email=form.email.data).first()
        if user is None:
            form.email.errors.append("User not found!")
            return flask.render_template("login.html", form=form)
        if not check_password_hash(user.auth_hash, form.password.data):
            form.password.errors.append("Invalid Password!")
            return flask.render_template("login.html", form=form)
        login_user(user, remember=True)
        flask.flash("Logged in successfully.")
        return flask.redirect(
            flask.request.args.get("next") or
            flask.url_for("get_hash")
        )
    return flask.render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return flask.redirect(flask.url_for('login'))

@app.route(u'/', methods=('GET', 'POST'))
@app.route(u'/<paste_hash>', methods=('GET', 'POST'))
def get_hash(paste_hash = None):
    if current_user.is_anonymous():
        form = CaptchaPaste()
    else:
        form = Paste()
    if form.validate_on_submit():
        paste_data = form.paste_content.data
        paste_title = form.title.data
        paste_author = form.author.data
        digestable_message = u"%s%s%s" % (
            paste_author,
            paste_title,
            paste_data
        )
        new_paste_hash = sha1(digestable_message).hexdigest()
        if new_paste_hash != paste_hash:
            if form.language.data == u'none':
                language = guess_lexer(form.paste_content.data).aliases[0]
            else:
                language = form.language.data
            save_paste(
                new_paste_hash,
                paste_data,
                language = language,
                title = paste_title,
                author = paste_author,
                expire_in = int(form.expire_time.data)
            )
            return flask.redirect(
                flask.url_for(
                    'get_hash',
                    paste_hash = new_paste_hash
                )
            )
    fill_form_from_db(paste_hash, form)
    if not form.paste_content.data:
        return flask.render_template(
            'base.html',
            form = form,
            message = highlight_content(u"Create a new paste!", u'text')
        )
    hilighted_data = highlight_content(form.paste_content.data)
    rendered_page = flask.render_template(
        'base.html',
        form = form,
        message = hilighted_data
    )
    return rendered_page

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
