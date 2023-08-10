# app.py

import pathlib
from flask import Flask,flash, render_template, request,jsonify,session,redirect,abort
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

# GOOGLE_CLIENT_ID="937161169077-o7l3qal4gbq1bnrnrjn6se2ulvhe8g8r.apps.googleusercontent.com"

# client_secrets_file = os.path.join(pathlib.Path(__file__).parent,"client-secret.json")

# flow = Flow.from_client_secrets_file(
#     client_secrets_file=client_secrets_file,
#     scopes=["https://www.googleapis.com/auth/userinfo.profile","https://www.googleapis.com/auth/userinfo.email","openid"],
#     redirect_uri="http://127.0.0.1:5000/submit"
#     )
questions_file_path = os.path.join(os.path.dirname(__file__), 'questions.txt')
openai.api_key = os.getenv("OPENAI_API_KEY")

prompt1 = '''Evaluate the question and answer below and assign a score out of 100 for each question.
 20% of the score should depend on the grammar of the answer.
 20% on the length of the answer (deduct more points if the length is less than 50 words.).
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

# Set up the database connection
def create_conn():
    return mysql.connector.connect(
        host="metaintrospec.mysql.pythonanywhere-services.com",
        user="metaintrospec",
        password=os.getenv('SQL_PASS'),
        database="metaintrospec$students"
    )

@app.route('/', methods=['GET', 'POST'])
def details():
    # authorization_url,state = flow.authorization_url()
    # session["state"] = state
    return render_template("details.html")

@app.route('/save', methods=['POST'])
def save_details():

    if request.method == 'POST':
        # Process form submission
        name = request.form["name"]
        email = request.form["email"]
        gender = request.form['gender']

        conn = create_conn()
        cursor = conn.cursor()

        query = "SELECT attempt_count FROM student_details WHERE email = %s"

        cursor.execute(query, (email,))
        attempt_count= cursor.fetchone()

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

            return render_template('index.html', questions=questions[index:index+5],email=email,count=attempt_count[0],name=name)

    return render_template('details.html')


@app.route('/index', methods=['POST'])
def index():

    if request.method == 'POST':
        name=request.form.get('name')
        email = request.form.get('email')
        questions=request.form.get('questions')

        attempt_count= validate_user(email)

        answers = {f'answer{i}': request.form[f'answer{i}'] for i in range(attempt_count*5+1, attempt_count*5+6)}
        answers_json = json.dumps(answers)


        message= get_scores(questions,answers)
        # # Extract the text from "choices"
        text_from_choices = message["choices"][0]["message"]["content"]
        print("gpt score",text_from_choices)

        # # Split the text based on ", " to separate the key-value pairs
        items = text_from_choices.strip().split(", ")
        # print(items)
        # # Initialize a variable to store the total score
        total_score = 0

        # # Loop through the items and add up the scores
        for item in items:
            key, value = item.split(":")
            score = float(value.strip().replace("%", ""))
            print(score)
            total_score += score

        # # Calculate the average score
        average_score = total_score / len(items)

        # # Output the average score
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


        return render_template('score.html',score=average_score,name= name)
    return render_template('answers.html', questions=questions)


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
    print(response)
    return response

if __name__ == '__main__':
  app.run(debug=True)

