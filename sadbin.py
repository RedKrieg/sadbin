#!/usr/bin/env python

from hashlib import sha1
from flask.ext.bootstrap import Bootstrap
from flask.ext.redis import Redis
from flask.ext.wtf import Form
from wtforms import TextField, TextAreaField
from wtforms.validators import Length, InputRequired
import flask

app = flask.Flask(__name__)
app.config.from_pyfile('instance/application.cfg')
redis = Redis(app)
Bootstrap(app)

# Defaults
if 'MAX_UPLOAD_SIZE' not in app.config:
    app.config['MAX_UPLOAD_SIZE'] = 2**18
if 'DEFAULT_EXPIRE_TIME' not in app.config:
    app.config['DEFAULT_EXPIRE_TIME'] = 3600 * 365

class Paste(Form):
    paste_content = TextAreaField(
        'Paste Data:',
        [
            Length(
                max = app.config['MAX_UPLOAD_SIZE'],
                message = "Max upload size is %dKiB" % (
                    app.config['MAX_UPLOAD_SIZE'] / 1024
                )
            ),
            InputRequired(
                message = "You must enter data."
            )
        ]
    )

def set_key(key, data, expire_in = None):
    if not expire_in:
        expire_in = app.config['DEFAULT_EXPIRE_TIME']
    redis.set(key, data)
    if expire_in != -1:
        redis.expire(key, expire_in)

@app.route('/', methods=('GET', 'POST'))
def main():
    form = Paste()
    if form.validate_on_submit():
        paste_data = form.paste_content.data
        paste_hash = sha1(paste_data).hexdigest()
        set_key(paste_hash, paste_data)
        return flask.redirect(flask.url_for('get_hash', paste_hash = paste_hash))
    return flask.render_template('base.html', form=form, message="Nothing")

@app.route('/<paste_hash>', methods=('GET', 'POST'))
def get_hash(paste_hash = None):
    if not paste_hash:
        return flask.redirect(flask.url_for('main'))
    form = Paste()
    if form.validate_on_submit():
        paste_data = form.paste_content.data
        new_paste_hash = sha1(paste_data).hexdigest()
        if new_paste_hash != paste_hash:
            set_key(new_paste_hash, paste_data)
            return flask.redirect(
                flask.url_for(
                    'get_hash',
                    paste_hash = paste_hash
                )
            )
    form.paste_content.data = redis.get(paste_hash)
    return flask.render_template(
        'base.html',
        form = form,
        message = form.paste_content.data
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
