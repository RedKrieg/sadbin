#!/usr/bin/env python

from flask.ext.bootstrap import Bootstrap
from flask.ext.wtf import Form
from wtforms import TextAreaField
import flask

app = flask.Flask(__name__)
app.config.from_pyfile('instance/application.cfg')

class Paste(Form):
    paste_content = TextAreaField('Paste Data:')

@app.route('/', methods=('GET', 'POST'))
def main():
    form = Paste()
    if form.validate_on_submit():
        return flask.render_template('base.html', form=form,
                                     message=form.paste_content.data)
    return flask.render_template('base.html', form=form, message="Nothing")

Bootstrap(app)
if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
