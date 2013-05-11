#!/usr/bin/env python

from hashlib import sha1
from flask.ext.bootstrap import Bootstrap
from flask.ext.redis import Redis
from flask.ext.wtf import Form
from wtforms import TextField, TextAreaField, SelectField
from wtforms.validators import Length, InputRequired, NumberRange
from pygments import highlight
from pygments.lexers import guess_lexer, get_lexer_by_name, get_all_lexers
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from humanize import naturalday, naturaltime
import flask, datetime

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

class Paste(Form):
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

def save_paste(key, paste_data, language = u'none', expire_in = None):
    if not expire_in:
        expire_in = app.config['DEFAULT_EXPIRE_TIME']
    data = {
        'paste_content': paste_data,
        'language': language
    }
    redis.hmset(key, data)
    if expire_in > 0:
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
    """Fills a form from the database, returns True if we had to append
    something to the expire_time field of the form."""
    data = redis.hgetall(key)
    for field in [ i.name for i in form ]:
        try:
            form[field].data = data[field]
        except:
            pass # Leave default values
    ttl = redis.ttl(key)
    form.expire_time.data = u'%d' % ttl
    if form.expire_time.data not in [ i[0] for i in form.expire_time.choices ]:
        now = datetime.datetime.now()
        form.expire_time.choices.append((
            form.expire_time.data,
            naturaltime(now + datetime.timedelta(seconds=ttl)).capitalize()
        ))
        return True
    return False

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
                language = language,
                expire_in = int(form.expire_time.data)
            )
            return flask.redirect(
                flask.url_for(
                    'get_hash',
                    paste_hash = new_paste_hash
                )
            )
    pop_expire = fill_form_from_db(paste_hash, form)
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
    if pop_expire:
        form.expire_time.choices.pop()
    return rendered_page

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
