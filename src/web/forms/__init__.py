from flask_wtf import FlaskForm
from wtforms import SubmitField

class ToggleSaveForm(FlaskForm):
    submit = SubmitField('Toggle Save')

class ScanNewsForm(FlaskForm):
    submit = SubmitField('Scan News')

class ResetDBForm(FlaskForm):
    submit = SubmitField('Reset Database')