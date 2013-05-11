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

@app.route('/', methods=('GET', 'POST'))
def main():
    form = Paste()
    if form.validate_on_submit():
        return flask.render_template('base.html', form=form,
                                     message=form.paste_content.data)
    return flask.render_template('base.html', form=form, message="Nothing")

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
