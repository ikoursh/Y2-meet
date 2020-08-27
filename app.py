

# Start sequence

print("--------------------------------------------")
print("|               Initializing               |")
print("|                                          |")
print("|                                          |")
print("| Attempting to import dependencies        |")

# Imports
import datetime
import json
import os
import random
import string
from functools import wraps

import firebase_admin
import flask
from firebase_admin import credentials, auth, exceptions, firestore
from flask import Flask, request, render_template, flash, url_for, redirect, send_file  # App configuration

from werkzeug.utils import secure_filename
from locationiq.geocoder import LocationIQ


print("|                                          |")
print("| Attempting to get API key for location IQ|")

try:
    f = open("location_IQ_api.txt", "r")
    key = f.read()
    print(key)
    geocoder = LocationIQ(key)
    f.close()
except:
    print("\nFailed to get IQ API KEY")
    exit(-1)
print("| [OK]                                     |")
print("|                                          |")
print("| Attempting to get API key for firebase   |")
try:
    cred = credentials.Certificate('fbadminconfig.json')
    firebase = firebase_admin.initialize_app(cred)
except:
    print("\nUnable to get firebase api key")
    exit(-1)
print("| [OK]                                     |")
print("--------------------------------------------")


# Config:
UPLOAD_FOLDER = 'static/usr_imgs'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)  # Connect to firebase
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


db = firestore.client()


# user login backend
@app.route('/sessionLogin', methods=['POST'])
def session_login():
    # Get the ID token sent by the client
    id_token = request.get_json(force=True)['idToken']
    # Set session expiration to 5 days.

    auth.create_user()
    expires_in = datetime.timedelta(days=5)
    try:
        print("login attempt with id token: " + id_token)
        # Create the session cookie. This will also verify the ID token in the process.
        # The session cookie will have the same claims as the ID token.
        session_cookie = auth.create_session_cookie(id_token, expires_in=expires_in)

        response = app.response_class(
            response=json.dumps({'status': 'success'}),
            status=200,
            mimetype='application/json'
        )

        # response = flask.jsonify({'status': 'success', 'email_v': email_v})

        # Set cookie policy for session cookie.
        expires = datetime.datetime.now() + expires_in
        response.set_cookie(
            'session', session_cookie, expires=expires, httponly=True, secure=True)

        print("new session! ", session_cookie)

        return response
    except exceptions.FirebaseError:
        return flask.abort(401, 'Failed to create a session cookie')


# annotation to require login
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


# show volunteering opportunities
@app.route("/volunteer")
def volunteer():
    users_ref = db.collection('opportunities')
    docs = users_ref.stream()
    data = []
    for doc in docs:
        pd = doc.to_dict()
        pd["id"] = doc.id
        data.append(pd)
    print(data)
    return render_template("volunteer.html", data=data)


# show images
@app.route("/image/<string:path>")
def image(path):
    return send_file(os.path.join("static", "usr_imgs", secure_filename(path)), mimetype="image")


# show a volunteering opportunity
@require_login
@app.route("/opportunity/<string:oid>")
def opportunity(oid):
    doc_ref = db.collection(u'opportunities').document(oid)
    doc = doc_ref.get()
    if doc.exists:
        return render_template("opportunity.html", data=doc.to_dict())
    else:
        return "unauthorized"  # page_not_found()


# get user data
def get_user():
    try:
        return auth.verify_session_cookie(flask.request.cookies.get('session'), check_revoked=True)
    except:
        return False


# check if the file is allowed to be uploaded
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# generate a unique filename
def uniqe_fn():
    fn = ''.join(random.choice(string.ascii_letters) for i in range(10))
    return fn if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], fn)) else uniqe_fn()


# create a new post
@app.route("/post", methods=['POST', 'GET'])
@app.route("/create", methods=['POST', 'GET'])
def create():
    lvl = admin_level()
    if lvl == 0:
        return "unauthorized"
    if request.method == "GET":
        return render_template("create.html")

    title = request.form["title"]
    desc = request.form["description"]
    text = request.form["text"]
    # geocoder.geocode(‘Charminar Hyderabad’)
    location = request.form["location"]

    if 'image' not in request.files:
        return redirect(url_for("home"))
    file = request.files['image']
    # if user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        return redirect(url_for("create"))
    if not (file and allowed_file(file.filename)):
        return redirect(url_for("create"))
    filename = uniqe_fn()
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    doc_ref = db.collection(u'opportunities').add({
        "title": title,
        "desc": desc,
        "text": text,
        "img": "/image/" + filename
    })

    return redirect("/opportunity/" + str(doc_ref[1].id))  # redirect to new id


# create a new post
@app.route("/admin", methods=['GET'])
def admin():
    lvl = admin_level()
    if int(lvl) < 5:
        return "unauthorized"

    users_ref = db.collection('admins')
    admins = users_ref.stream()
    users = []
    for a in admins:
        try:
            u = auth.get_user(a.id)
            users.append({
                "uid": a.id,
                "name": u.display_name,
                "img": u.photo_url,
                "email": u.email,
                "lvl": a.to_dict()["level"]
            })
        except firebase_admin._auth_utils.UserNotFoundError:
            pass
    print(users[0])
    return render_template("admin.html", users=users)


@app.route("/remove_admin", methods=["post"])
def remove_admin():
    print("remove admin")
    if int(admin_level()) < 5:
        return "unauthorized"
    print(request.get_json(force=True)['uid'])
    db.collection(u'admins').document(request.get_json(force=True)['uid']).delete()
    return redirect(url_for("admin"))


@app.route("/create_admin", methods=["post"])
def create_admin():
    if int(admin_level()) < 5:
        return "unauthorized"
    print(0)
    rj = request.form.to_dict()
    print(rj)
    db.collection(u'admins').document(auth.get_user_by_email(rj["email"]).uid).set({"level": rj["level"]})
    print(2)
    return redirect(url_for("admin"))


# get the permission level of a user
def admin_level() -> int:
    if not get_user():
        return 0
    doc_ref = db.collection(u'admins').document(get_user()["uid"])
    doc = doc_ref.get()
    if not doc.exists:
        return 0
    return doc.to_dict()["level"]


# login
@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/restricted")
@require_login
def restricted():
    if not get_user():
        return "bad access"
    return "good access " + str(get_user())


@app.route("/")
@app.route("/home")
@app.route("/logged_in")
def home():
    return render_template("home.html")


if __name__ == '__main__':
    app.run(debug=True, host="localhost")
