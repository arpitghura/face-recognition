import os
import zlib
from base64 import b64decode

import face_recognition
from firebase_admin import credentials, db, initialize_app, storage
from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from flask_session import Session
from helper import login_required

# authorizing app to firebase storage and Database
cred = credentials.Certificate('./face-recognition-01-firebase-adminsdk-3u81p-c07aed38f7.json')
databaseURL = 'https://face-recognition-01-default-rtdb.firebaseio.com/'
initialize_app(cred, {'storageBucket': 'face-recognition-01.appspot.com', 'databaseURL': databaseURL})

# creating app session configuration for flask
app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


@app.route('/')
def index():
    if('user' in session):
        return render_template('index.html', user_session=session['user'])
    else:
        session.clear()
        return render_template('index.html')


@app.route('/dashboard')
@login_required  # to check whether the user is already logged in or not
def dashboard():
    return render_template('dashboard.html')


@app.route('/signin', methods=['POST', 'GET'])
def login():
    # clearing the session
    session.clear()
    # checking if the request is post or get
    if request.method == 'POST':
        # get the data from the form and store in variables
        userDetails = request.form
        form_username = userDetails['username']
        form_password = userDetails['password']
        # Validating the user password
        if len(form_password) < 8:
            return render_template('login.html', passerror="Password must be atleast 8 characters long")
        else:
            # check if the user is registered or not
            ref = db.reference("/users/"+form_username)
            account = ref.get()
            # saving user password in variable
            acc_password = account['password']
            if account:
                # checking if the password is correct or not
                if not check_password_hash(acc_password, form_password):
                    return render_template("login.html", passerror="Username or Password is incorrect")
                else:
                    # Remember which user has logged in using session
                    session["user"] = account
                    # redirecting user to dashboard page
                    return redirect(url_for('dashboard'))
            else:
                return render_template("login.html", passerror="User Not Registered")
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def register():
    # clearing the session
    session.clear()
    # checking if the request is post or get
    if request.method == 'POST':
        # get the data from the form and store in variables
        userDetails = request.form
        username = userDetails['username']
        name = userDetails['name']
        password = userDetails['password']
        email = userDetails['email']
        confirm_password = userDetails['confirm_password']

        # checking if the password and confirm password are same
        if password != confirm_password:
            return render_template('register.html', pwderror='Passwords do not match')

        # Validating the user password length
        elif len(password) < 8:
            return render_template('register.html', pwderror="Password must be atleast 8 characters long")

        else:
            # referencing the firebase realtime database
            ref = db.reference("/users/"+username)
            # checking if the user is already registered or not
            account = ref.get()
            if not account:
                # making a dictionary to store the user data and updating it on firebase database
                ref.set({
                    'username': username,
                    'name': name,
                    'email': email,
                    'password': generate_password_hash(password, method='pbkdf2:sha256', salt_length=8),
                    'image': ''
                })
                # returning user to login page after registration
                return redirect(url_for('login'))

            elif account.get('username') == username:
                # returning user to register page if the username is already registered with error
                return render_template('register.html', usernameerror=1)
            elif account.get('email') == email:
                # returning user to register page if email is already registered with error
                return render_template('register.html', accerror=1)

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    # clear the session and redirect to home page
    session.clear()
    return redirect('/')


@app.route("/facerecog", methods=["GET", "POST"])
def facerecog():
    # clearing the session
    session.clear()
    # checking if the request is post or get
    if request.method == "POST":
        # Get form data and store in variables
        encoded_image = (request.form.get("pic")+"==").encode('utf-8')
        # getting username from user
        form_username = request.form.get("username")
        
        # referincing the firebase storage
        ref = db.reference("/users/"+form_username)
        # checking if the user is already registered or not
        account = ref.get()
        if not account:
            return render_template("facerecog.html", message="No such user found")
        elif account.get('image') == "":
            return render_template("facerecog.html", message="Not set face recogonition yet")
        
        # store username in variable
        account_username = account.get('username')
        # compressing and uncompressing the image to remove several info and to reduce size
        compressed_data = zlib.compress(encoded_image, 9)
        uncompressed_data = zlib.decompress(compressed_data)
        # decoding the image
        decoded_data = b64decode(uncompressed_data)
        # taking reference of path where the image need to save
        new_image_handle = open('./static/face/unknown/'+str(account_username)+'-unknown.jpg', 'wb')
        # saving and closing the handler
        new_image_handle.write(decoded_data)
        new_image_handle.close()
        # downloading the image from firebase storage
        bucket = storage.bucket()
        blob = bucket.blob(str(account_username)+'.jpg')
        blob.download_to_filename('./static/face/'+str(account_username)+'.jpg')

        # load the downloaded image into face_recognition
        saved_image_of_user = face_recognition.load_image_file('./static/face/'+str(account_username)+'.jpg')
    
        # getting the face encodings of the image
        saved_image_encoding = face_recognition.face_encodings(saved_image_of_user)[0]
        # loading the unknown image
        unknown_image = face_recognition.load_image_file('./static/face/unknown/'+str(account_username)+'-unknown.jpg')
        try:
            # getting the face encodings of the unknown image
            unknown_face_encoding = face_recognition.face_encodings(unknown_image)[0]
        except :
            return render_template("facerecog.html", message="Image is not clear")

        # compare faces of both images by their encodings
        results = face_recognition.compare_faces([saved_image_encoding], unknown_face_encoding)
        # if the result is true then the face is same
        if results[0]:
            # clearing the previous session
            session.clear()
            # creating the new session for the user logged in via face id
            session['user'] = account
            return redirect(url_for("dashboard"))
        else:
            return render_template("facerecog.html", message="Incorrect face")
    else:
        return render_template("facerecog.html")


@app.route("/facesetup", methods=["GET", "POST"])
@login_required
def facesetup():
    # checking the user have already settupped the face recognition or not
    if session['user'].get('image'):
        return render_template("facesetup.html", imagemsg="Face Recognition already setupped!")
    else:
        if request.method == "POST":
            # Get form data
            encoded_image = (request.form.get("pic")+"==").encode('utf-8')
            # compressing and uncompressing the image to remove several info and to reduce size
            compressed_data = zlib.compress(encoded_image, 9)
            uncompressed_data = zlib.decompress(compressed_data)
            # decoding the image
            decoded_data = b64decode(uncompressed_data)
            # getting the username from the session
            account_username = session['user']['username']
            # handler to store the path for the image
            new_image_handle = open(
                './static/face/'+str(account_username)+'.jpg', 'wb')
            # saving the image at the specified path
            new_image_handle.write(decoded_data)
            new_image_handle.close()

            # loading the unknown image by face_recognition
            taken_image = face_recognition.load_image_file('./static/face/'+str(account_username)+'.jpg')
            try:
                # getting the face encodings of the taken image
                taken_image_encoding = face_recognition.face_encodings(taken_image)[0]
            except:
                return render_template("facesetup.html", message=1)
            else:
                print(taken_image_encoding)
                if [taken_image_encoding]:
                    # uploading file to firebase
                    file_name = 'static/face/'+str(account_username)+'.jpg'
                    bucket = storage.bucket()
                    blob = bucket.blob(str(account_username)+'.jpg')
                    blob.upload_from_filename(file_name)
                    # making the uploaded file public
                    blob.make_public()
                    # storing the user image url to the session
                    session['user']['image'] = blob.public_url

                    # getting reference of the firebase database
                    ref = db.reference("/users/"+account_username)
                    # update the image data to the photo public url
                    ref.update({'image': blob.public_url})
                    os.remove('./static/face/'+str(account_username)+'.jpg')
                    # redirecting user to the dashboard
                    return redirect("/dashboard")
                else:
                    return render_template("facesetup.html", message=1)
        else:
            return render_template("facesetup.html")

if __name__ == '__main__':
    app.run()
