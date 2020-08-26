# Imports
import datetime
from functools import wraps

import firebase_admin
import flask
from firebase_admin import credentials, auth, exceptions
from flask import Flask, request, render_template  # App configuration

app = Flask(__name__)  # Connect to firebase
cred = credentials.Certificate('fbAdminConfig.json')  # TODO: limit permissions to service account
firebase = firebase_admin.initialize_app(cred)


@app.route('/sessionLogin', methods=['POST'])
def session_login():
    # Get the ID token sent by the client
    id_token = request.get_json(force=True)['idToken']
    # Set session expiration to 5 days.
    expires_in = datetime.timedelta(days=5)
    try:
        print("login attempt with id token: "+id_token)
        # Create the session cookie. This will also verify the ID token in the process.
        # The session cookie will have the same claims as the ID token.
        session_cookie = auth.create_session_cookie(id_token, expires_in=expires_in)
        response = flask.jsonify({'status': 'success'})
        # Set cookie policy for session cookie.
        expires = datetime.datetime.now() + expires_in
        response.set_cookie(
            'session', session_cookie, expires=expires, httponly=True, secure=True)

        print("new session! ", session_cookie)
        return response
    except exceptions.FirebaseError:
        return flask.abort(401, 'Failed to create a session cookie')


def require_login(f):
    @wraps(f)
    def access_restricted_content(*args, **kwargs):
        session_cookie = flask.request.cookies.get('session')
        if not session_cookie:
            # Session cookie is unavailable. Force user to login.
            return flask.redirect('/login')

        # Verify the session cookie. In this case an additional check is added to detect
        # if the user's Firebase session was revoked, user deleted/disabled, etc.
        try:
            decoded_claims = auth.verify_session_cookie(session_cookie, check_revoked=True)
            print(decoded_claims)
            return f(*args, **kwargs)
        except auth.InvalidSessionCookieError:
            # Session cookie is invalid, expired or revoked. Force user to login.
            return flask.redirect('/login')

    return access_restricted_content


def get_user():
    try:
        return auth.verify_session_cookie(flask.request.cookies.get('session'), check_revoked=True)
    except:
        return False




@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/logged_in")
@app.route("/restricted")
@require_login
def restricted():
    if not get_user():
        return "bad access"
    return "good access " + str(get_user())


@app.route("/")
@app.route("/home")
def home():
    return "hello world"


if __name__ == '__main__':
    app.run(debug=True, host="localhost")
