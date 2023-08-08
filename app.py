# app.py

import pathlib
from flask import Flask, render_template, request,jsonify,session,redirect,abort
import mysql.connector
import requests
import json
import os
import openai
from pip._vendor import cachecontrol
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests
import google
from google.oauth2 import id_token

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)
app.secret_key = "students_help"

GOOGLE_CLIENT_ID="937161169077-o7l3qal4gbq1bnrnrjn6se2ulvhe8g8r.apps.googleusercontent.com"

client_secrets_file = os.path.join(pathlib.Path(__file__).parent,"client-secret.json")

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    scopes=["https://www.googleapis.com/auth/userinfo.profile","https://www.googleapis.com/auth/userinfo.email","openid"],
    redirect_uri="http://kavyakonisa.pythonanywhere.com/submit"
    )


questions_file_path = os.path.join(os.path.dirname(__file__), 'questions.txt')
openai.api_key = "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"

prompt1 = '''Evaluate the question and answer below and assign a score out of 100 for each question.
 20% of the score should depend on the grammar of the answer.
 20% on the length of the answer (deduct more points if the length is less than 20 words.).
 50% on the relevancy of the answer to the question. use your own metrics to figure this out. 10% based on how genuine the answer looks. Your job is to analyze the question and answer and give your score for each of the metrics above.  the final score should be weighted average of all the 4 scores'. Your output should only contain the following: "question1: {your final score},questions2:{your final score} ...".
Nothing else should be in the output.
Here are the questions and answers below:
"'''

try:
    with open(questions_file_path) as f:
        questions = f.readlines()
        print(questions)
except FileNotFoundError:
    print("The 'questions.txt' file is missing or not found.")
print(questions)

# Set up the database connection
def create_conn():
    return mysql.connector.connect(
        host="kavyakonisa.mysql.pythonanywhere-services.com",
        user="kavyakonisa",
        password="priyakavya",
        database="kavyakonisa$students"
    )


@app.route('/', methods=['GET', 'POST'])
def details():
    authorization_url,state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route('/submit', methods=['GET','POST'])
def submit_details():
    print(request.method)
    flow.fetch_token(authorization_response=request.url)

    if not session['state'] == request.args["state"]:
        abort(500)

    credentials = flow.credentials
    print(credentials)
    request_session = requests.session()
    cached_session  = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)
    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID
    )

    session["google_id"] = id_info.get("sub")
    session["name"] = id_info.get("name")
    session["email"] = id_info.get("email")

    return render_template("details.html")

@app.route('/save', methods=['POST'])
def save_details():
    print(request.method)
    if request.method == 'POST':
        # Process form submission
        name = session["name"]
        email = session["email"]
        gender = request.form['gender']
        print(name,email,gender)
        conn = create_conn()
        cursor = conn.cursor()

        query = "SELECT attempt_count FROM student_details WHERE email = %s"

        cursor.execute(query, (email,))
        attempt_count= cursor.fetchone()
        print(attempt_count)
        if attempt_count is None:
            # Insert the new record if the email is not present
            insert_query = "INSERT INTO student_details (name, email, gender,attempt_count) VALUES (%s,%s, %s, %s)"
            cursor.execute(insert_query, (name, email,gender, 0))
            conn.commit()
            cursor.close()
            conn.close()
            return render_template('index.html', questions=questions[0:5],email=email,count=0,name=name)
        else:
            index=attempt_count[0]*5
            print(attempt_count[0])
            return render_template('index.html', questions=questions[index:index+5],email=email,count=attempt_count[0],name=name)

    return render_template('details.html')


@app.route('/index', methods=['POST'])
def index():
    print("Helloworld")
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        print(email)
        attempt_count= validate_user(email)
        print(attempt_count)
        answers = {f'answer{i}': request.form[f'answer{i}'] for i in range(attempt_count*5+1, attempt_count*5+6)}
        answers_json = json.dumps(answers)
        print(answers)
        message= get_scores(questions,answers)
        print("gpt response", message)
        # Extract the text from "choices"
        text_from_choices = message["choices"][0]["message"]["content"]
        print("gpt score",text_from_choices)

        # Split the text based on ", " to separate the key-value pairs
        items = text_from_choices.strip().split(", ")

        # Initialize a variable to store the total score
        total_score = 0

        # Loop through the items and add up the scores
        for item in items:
            key, value = item.split(":")
            score = float(value.strip().replace("%", ""))
            total_score += score

        # Calculate the average score
        average_score = total_score / len(items)

        # Output the average score
        print("Average score:", average_score)
        conn = create_conn()
        cursor = conn.cursor()

        query = "INSERT INTO student_eval (email, answers, score) VALUES (%s, %s,%s)"
        cursor.execute(query, ( email, answers_json,int(average_score)))

        conn.commit()

        update_query = "UPDATE student_details SET attempt_count = attempt_count + 1 WHERE email = %s"
        cursor.execute(update_query, (email,))
        conn.commit()
        cursor.close()
        conn.close()

        return render_template('score.html',score=int(average_score),name=name)
    return render_template('index.html', questions=questions)

def validate_user(email):
    conn = create_conn()
    cursor = conn.cursor()
    query = "SELECT attempt_count FROM student_details WHERE email = %s"
    cursor.execute(query, (email,))
    attempt_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return attempt_count

def get_scores(questions,answers):
    response= openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role":"user","content":prompt1 + "Questions" +  "".join(questions) + "Answers"+ str(answers)}
    ],
    max_tokens=100,
    )
    return response

if __name__ == '__main__':
  app.run(debug=True, port=5001)

