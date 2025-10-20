from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_text = request.form['text_input']
        return redirect(url_for('label', text=user_text))
    return render_template('index.html')

@app.route('/label')
def label():
    user_text = request.args.get('text', '')
    return render_template('label.html', text=user_text)

if __name__ == '__main__':
    app.run(debug=True)