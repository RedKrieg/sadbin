#!/usr/bin/env python

from hashlib import sha1
from flask.ext.bootstrap import Bootstrap
from flask.ext.redis import Redis
from flask.ext.wtf import Form
from wtforms import TextField, TextAreaField, SelectField
from wtforms.validators import Length, InputRequired
from pygments import highlight
from pygments.lexers import guess_lexer, get_lexer_by_name, get_all_lexers
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
import flask

app = flask.Flask(__name__)
app.config.from_pyfile(u'instance/application.cfg')
redis = Redis(app)
Bootstrap(app)

# Defaults
if 'MAX_UPLOAD_SIZE' not in app.config:
    app.config['MAX_UPLOAD_SIZE'] = 2**18
if 'DEFAULT_EXPIRE_TIME' not in app.config:
    app.config['DEFAULT_EXPIRE_TIME'] = 3600 * 365

def get_lexer_list():
    """Iterator which yeilds the first lexer short-name and the lexer long
    name as a two-tuple."""
    yield ('none',"Guess Language")
    for lexer in sorted(get_all_lexers(), key=lambda x: x[0].lower()):
        yield lexer[1][0], lexer[0]

class Paste(Form):
    language = SelectField(
        'Language:',
        choices = [ i for i in get_lexer_list() ]
    )
    paste_content = TextAreaField(
        'Paste Data:',
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

def save_paste(key, paste_data, language = u'none', expire_in = None):
    if not expire_in:
        expire_in = app.config['DEFAULT_EXPIRE_TIME']
    data = {
        'paste_content': paste_data,
        'language': language
    }
    redis.hmset(key, data)
    if expire_in != -1:
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
    return highlight(content, lexer, formatter)

def fill_form_from_db(key, form):
    data = redis.hgetall(key)
    for field in [ i.name for i in form ]:
        try:
            form[field].data = data[field]
        except:
            pass # Leave default values

@app.route(u'/', methods=('GET', 'POST'))
@app.route(u'/<paste_hash>', methods=('GET', 'POST'))
def get_hash(paste_hash = None):
    form = Paste()
    if form.validate_on_submit():
        paste_data = form.paste_content.data
        new_paste_hash = sha1(paste_data).hexdigest()
        if new_paste_hash != paste_hash:
            if form.language.data == u'none':
                language = guess_lexer(form.paste_content.data).aliases[0]
            else:
                language = form.language.data
            save_paste(
                new_paste_hash,
                paste_data,
                language = language
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
    return flask.render_template(
        'base.html',
        form = form,
        message = hilighted_data
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
