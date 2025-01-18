import datetime
from flask import Flask, render_template, request, redirect, url_for, session
import time
import json
import os
import smtplib
import ssl
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
import threading
import requests


app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATA_FILE = 'members_data.json'
RESPONSES_DIR = 'responses'

# Email settings
smtp_server = 'smtp-relay.brevo.com'
smtp_port = 587
sender_email = "839e9a001@smtp-brevo.com"  # Remplacez par votre clé API Mailjet
sender_password = "adVkWshHnqIU1CFD" # Remplacez par votre clé secrète API Mailjet
sender_email_real = "synapsemohamed@gmail.com" # Remplacez par votre adresse email vérifiée sur Mailjet

class QCM:
    def __init__(self, id, question, propositions, correct_answers, user_answers=None, results=None, done=False, time_elapsed=0, cours=1):
        self.id = id
        self.question = question
        self.propositions = propositions
        self.correct_answers = correct_answers
        self.user_answers = user_answers if user_answers is not None else []
        self.results = results
        self.done = done
        self.time_elapsed = time_elapsed
        self.cours = cours

    def validate(self, user_answers):
        self.user_answers = user_answers
        self.results = self.calculate_results()
        self.done = True

    def calculate_results(self):
        missing = list(set(self.correct_answers) - set(self.user_answers))
        incorrect = list(set(self.user_answers) - set(self.correct_answers))
        return {
            'selected': self.user_answers,
            'correct': self.correct_answers,
            'missing': missing,
            'incorrect': incorrect,
        }
    def calculate_moyenne(self):
        if self.results:
          if len(self.results['incorrect']) > 0 :
            return 0
          else :
            correct_count = len(set(self.user_answers) & set(self.correct_answers))
            return  correct_count / len(self.correct_answers) * 100 if len(self.correct_answers) > 0 else 0
        return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'question': self.question,
            'propositions': self.propositions,
            'correct_answers': self.correct_answers,
            'user_answers': self.user_answers,
            'results': self.results,
            'done': self.done,
            'time_elapsed' : self.time_elapsed,
             'cours' : self.cours
        }
    
    @staticmethod
    def from_dict(data):
        return QCM(data['id'], data['question'], data['propositions'], data['correct_answers'], data.get('user_answers', []), data.get('results'), data.get('done', False), data.get('time_elapsed', 0), data.get('cours',1))
class Certificat:
    def __init__(self, nom, moyenne=0):
        self.nom = nom
        self.moyenne = moyenne
    
    def to_dict(self):
        return {
            'nom': self.nom,
            'moyenne' : self.moyenne
            
        }
    @staticmethod
    def from_dict(data):
       return Certificat(data['nom'], data['moyenne'])


# Load QCM data from JSON files
def load_qcms(matiere):
    try:
        with open(f'{matiere}.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [QCM.from_dict(qcm_data) for qcm_data in data]
    except FileNotFoundError:
      return []

def temps_ecoule(start_time, paused_time=0):
    end_time = time.time()
    elapsed_time = end_time - start_time + paused_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)
    return f"{minutes:02}:{seconds:02}"

# Load MEMBERS data from JSON file
def load_members_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
              members = json.load(f)
            except json.JSONDecodeError:
               print(f"Error: Could not decode members data from {DATA_FILE}, creating new data.")
               members = {}
            # Ensure 'level' exists for every user, set to "PCEM1" if missing
            for username, data in members.items():
                if 'level' not in data:
                     print(f"Adding default level 'PCEM1' for user: {username}")
                     data['level'] = "PCEM1"
                if 'registration_date' not in data:
                     print(f"Adding default registration date for user: {username}")
                     data['registration_date'] = datetime.datetime.now().strftime('%d/%m/%Y')  # Changed here
            print("Data loaded:", len(members), "members") #LOG
            return members
    else:
         print("File does not exists", DATA_FILE) #LOG
         return {}

# Save MEMBERS data to JSON file
def save_members_data(members):
    print("Saving data, number of users", len(members)) #LOG
    with open(DATA_FILE, 'w') as f:
        json.dump(members, f, indent = 4)
        
MEMBERS = load_members_data()

def generate_confirmation_code():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))

def send_confirmation_email(email, username, code, level):
    message = MIMEMultipart("alternative")
    message["Subject"] = "Confirmation d'inscription"
    message["From"] = sender_email_real # Use sender_email_real here
    message["To"] = email
    
    html = f"""
    <html>
      <body>
        <p>Bonjour {username},</p>
        <p>Merci de vous être inscrit sur notre plateforme. Vous êtes en {level}. Veuillez utiliser le code suivant pour confirmer votre compte:</p>
        <p><strong>{code}</strong></p>
         <p>Pour confirmer votre compte veuillez cliquer sur le lien ci dessous: </p>
        <p><a href = "{request.url_root}verify?username={username}&code={code}"> Confirmer mon compte</a> </p>

      </body>
    </html>
    """

    part = MIMEText(html, "html")
    message.attach(part)
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls(context=context)
        server.login(sender_email, sender_password) # Use sender_email and sender_password for authentication
        server.sendmail(sender_email_real, email, message.as_string())

def save_user_response(username, matiere, qcm_id, user_answers, elapsed_time, cours):
    
    filename = f"{matiere}_qcm_{qcm_id}_cours_{cours}.json"
    filepath = os.path.join(RESPONSES_DIR, filename)
     # Load existing data if any. if none, it will be {}
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
              existing_data = json.load(f)
            except json.JSONDecodeError:
               existing_data = {}
    else :
       existing_data = {}
   
    existing_data[username] = {
            'user_answers' : user_answers
        }
    
    with open(filepath, 'w', encoding = 'utf-8') as f:
       json.dump( existing_data, f, ensure_ascii=False, indent=4)
        

@app.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    error = None
    register_error = None
    try:
      if request.method == 'POST':
          username = request.form['username']
          password = request.form['password']
          if username in MEMBERS and MEMBERS[username]['password'] == password and MEMBERS[username].get('is_active', False) :
              session['username'] = username
              # Load persisted data if it exists
              if username in MEMBERS :
                  user_data = MEMBERS[username]
                  session['level'] = user_data.get('level', "PCEM1")
                  session['certificats'] = user_data.get('certificats', {})
                  #Store initial state of QCMs as lists of dicts in the MEMBERS array
                  with open('module_structure.json', 'r', encoding='utf-8') as f:
                      modules = json.load(f)
                      semesters = modules[session['level']]
                  for semester, modules_list in semesters.items():
                    for module in modules_list:
                        if f'qcms_{module}' not in MEMBERS[username]:
                              MEMBERS[username][f'qcms_{module}'] = [qcm.to_dict() for qcm in load_qcms(module)]

              save_members_data(MEMBERS)
              return redirect(url_for('index'))
          elif username in MEMBERS and not MEMBERS[username].get('is_active', False):
              error = "Votre compte n'est pas encore validé. Veuillez vérifier votre email."
          else :
              error = 'Identifiant ou mot de passe incorrect'
    except Exception as e :
      print("Exception in /login:", e)
      error = "An unexpected error occured."
    return render_template('login.html', error=error, register_error = register_error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
       try :
         username = request.form['username']
         password = request.form['password']
         email = request.form['email']
         level = request.form['level']

         if not email.endswith('@gmail.com'):
           return render_template('login.html', register_error="L'email doit terminer par @etudiant-fmt.utm.tn")

         if username in MEMBERS:
           return render_template('login.html', register_error="Ce nom d'utilisateur existe déjà.")
         
         confirmation_code = generate_confirmation_code()
         print(f"Creating new user, username: {username}, email: {email}, level: {level}") #LOG
         MEMBERS[username] = {'password': password, 'email': email, 'is_active': False, 'confirmation_code': confirmation_code, 'level' : level, 'certificats':{}, 'registration_date': datetime.datetime.now().strftime('%d/%m/%Y')} #setting registration date
        
         with open('module_structure.json', 'r', encoding='utf-8') as f:
           modules = json.load(f)
         if level in modules :
            semesters = modules[level]
            for semester, modules_list in semesters.items() :
                for module in modules_list:
                   MEMBERS[username]['certificats'][module] = Certificat(module).to_dict()
                   qcms = load_qcms(module)
                   MEMBERS[username][f'qcms_{module}'] = [qcm.to_dict() for qcm in qcms]
                   for qcm in qcms:
                       filename = f"{module}_qcm_{qcm.id}_cours_{qcm.cours}.json"
                       filepath = os.path.join(RESPONSES_DIR, filename)
                       if not os.path.exists(filepath): # we avoid rewriting the file if already existing
                          with open(filepath, 'w', encoding = 'utf-8') as f: #create an empty file
                             json.dump( {}, f, ensure_ascii=False, indent=4)
         save_members_data(MEMBERS)
         print(f"User created and saved : username: {username}") #LOG
         send_confirmation_email(email, username, confirmation_code, level)
         return render_template('confirm.html', username = username, email = email)
       except Exception as e:
          print(f"Exception in /register : {e}")
          return render_template('login.html', register_error="An unexpected error occured.")
    return render_template('register.html')

@app.route('/verify', methods = ['GET', 'POST'])
def verify_email():
    username = request.args.get('username')
    if request.method == 'POST':
         code = request.form['confirmation_code']
         if username in MEMBERS:
             if MEMBERS[username]['confirmation_code'] == code:
                MEMBERS[username]['is_active'] = True
                save_members_data(MEMBERS)
                return render_template('activate.html', message="Votre email a été confirmé. Vous pouvez vous connecter maintenant.")
             return render_template('confirm.html', username = username, email = MEMBERS[username]['email'], error = "Code de vérification incorrect.")

    return render_template('error.html', message="Utilisateur introuvable.")
    
def collect_and_calculate_percentages(qcms, current_qcm_index, matiere, cours):
    all_choices = defaultdict(lambda: [0] * len(qcms[current_qcm_index].propositions))
    qcm_id = qcms[current_qcm_index].id
    
    filepath = os.path.join(RESPONSES_DIR, f"{matiere}_qcm_{qcm_id}_cours_{cours}.json")
    if os.path.exists(filepath):
        try:
          with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for username, response_data in data.items():
                if 'user_answers' in response_data:
                   user_answers = response_data['user_answers']
                   for choice in user_answers:
                       if isinstance(choice, int) and choice < len(all_choices[username]):
                         all_choices[username][choice] = 1
            
        except (json.JSONDecodeError, FileNotFoundError):
            return [0] * len(qcms[current_qcm_index].propositions)

    percentages = [0] * len(qcms[current_qcm_index].propositions)
    total_users = len(all_choices)
    if total_users > 0:
        for index in range(len(qcms[current_qcm_index].propositions)):
          count = 0
          for user, choices in all_choices.items():
              count += choices[index]
          percentages[index] = (count / total_users) * 100
    return percentages


def calculate_rankings(level=None, filter_matiere=None, filter_semester=None):
    print(f"Calculating rankings for level={level}, filter_matiere={filter_matiere}, filter_semester={filter_semester}")
    rankings = {}

    for username, data in MEMBERS.items():
        user_level = data.get('level')
        print(f"Processing user {username} with level {user_level}")

        if level is not None and user_level != level:
            continue # Skip if levels do not match
        
        certificats = data.get('certificats', {})
        if not certificats:
            print(f"User {username} has no certificats.")
            continue

        total_moyenne = 0
        total_modules = 0
        matiere_moyenne = 0
        matiere_modules = 0
        
        for module, value in certificats.items():
            moyenne = value.get('moyenne', 0)
            print(f"Processing module {module} for user {username} with moyenne {moyenne}")
            
            if filter_semester :
               with open('module_structure.json', 'r', encoding='utf-8') as f:
                    modules = json.load(f)
               if level in modules:
                    semesters = modules[level]
                    for semester, modules_list in semesters.items():
                       if semester == filter_semester and module in modules_list :
                            matiere_moyenne += moyenne
                            matiere_modules += 1
            elif filter_matiere is None:
                total_moyenne += moyenne
                total_modules += 1
            elif filter_matiere == module:
                matiere_moyenne += moyenne
                matiere_modules += 1
        

        # Calcul des moyennes
        average = 0
        if filter_semester:
             if matiere_modules > 0:
               average = matiere_moyenne / matiere_modules
        elif filter_matiere is None:
          average = total_moyenne / total_modules if total_modules > 0 else 0
        elif matiere_modules > 0 :
          average = matiere_moyenne / matiere_modules 

        rankings[username] = {'moyenne': average}
        print(f"User {username} has average {average}")

    ranked_list = sorted(rankings.items(), key=lambda item: item[1]['moyenne'], reverse=True)
    
    
    
    print("Final Rankings:", ranked_list)
    return ranked_list

def organize_rankings_by_semester(level):
    with open('module_structure.json', 'r', encoding='utf-8') as f:
        modules = json.load(f)
    if level not in modules:
       return {}

    semesters = modules[level]
    semester_rankings = {}
    for semester, modules_list in semesters.items():
        ranked_list = calculate_rankings(level, filter_semester=semester) #get the rankings
        
        for index, (user, data) in enumerate(ranked_list): # add proper ranks
           ranked_list[index] = (user, data, index + 1) 
        semester_rankings[semester] = ranked_list
    return semester_rankings


def update_average_scores():
    if 'username' not in session:
        return
    
    username = session['username']

    if username not in MEMBERS: # Check if the username exists in MEMBERS
        return # Exit if not
        
    with open('module_structure.json', 'r', encoding='utf-8') as f:
        modules = json.load(f)
    if session['level'] in modules :
        semesters = modules[session['level']]
        for semester, modules_list in semesters.items() :
            for module in modules_list:
                #Load data for current session
                qcms = [QCM.from_dict(data) for data in MEMBERS[username].get(f'qcms_{module}',[])]

                total_score = 0
                for qcm in qcms:
                   moyenne = qcm.calculate_moyenne()
                   if moyenne is not None:
                      total_score += moyenne
                average_score = total_score / len(qcms) if qcms else 0
                average_score_20 = (average_score / 100) * 20
                if 'certificats' not in session :
                   session['certificats'] = {}
                if module not in session['certificats'] :
                    session['certificats'][module] = Certificat(module).to_dict()

                session['certificats'][module]['moyenne'] =  round(average_score_20, 2) if average_score_20 is not None else 0

    # Update the global MEMBERS data
    if username in MEMBERS:
        MEMBERS[username]['certificats'] = session['certificats']

    save_members_data(MEMBERS)

def calculate_global_success_rate(qcms):
    if not qcms:
        return 0.0, 0, 0  # Avoid division by zero

    total_correct = 0
    total_questions = 0
    for qcm in qcms:
        if qcm.results:
           
            correct_count = len(set(qcm.user_answers) & set(qcm.correct_answers))
            if correct_count == len(qcm.correct_answers):
              total_correct += 1
            total_questions += 1
    return (total_correct / total_questions) * 100 if total_questions > 0 else 0, total_correct, total_questions
def get_user_rank(matiere, level = None):
    if 'username' not in session:
        print("Error: Username not found in session for get_user_rank.")
        return "N/A"
    username = session['username']
    rankings = calculate_rankings(level, matiere)
    print(f"get_user_rank called for matiere: {matiere}, level: {level} , username: {username}, rankings : {rankings}")
    for index, (user, data) in enumerate(rankings):
        if user == username:
            print(f"User {username} found in rankings, rank: {index + 1}, data:{data}")
            return index + 1
    print(f"User {username} not found in rankings for matiere: {matiere}")
    return "N/A"


def get_top_rankings(username, rankings):
    top_5 = rankings[:5]
    user_found = any(user == username for user, _, _ in top_5)
    
    if not user_found:
        user_rank_data = next(((user, score, rank) for user, score, rank in rankings if user == username), None)
        if user_rank_data:
            # Insert the user at the first position with rank 1
            top_5 = [ (user_rank_data[0],user_rank_data[1], 1) ] + [item for item in top_5 if item[0] != username] #set rank 1 for current user and filter out from top 5
    else:
         user_rank_data = next(((user, score, rank) for user, score, rank in rankings if user == username), None)
    
    # Re-number ranks, since after putting the user first, the numbering may not be correct
    top_5_ranked = []
    for index, (user, score, rank) in enumerate(top_5):
        if user != username or not user_rank_data or not user_found: #do not change if user was already present
             top_5_ranked.append((user, score, index + 1))
        else :
            top_5_ranked.append((user, score, rank)) # keep initial rank if user was inserted first
    
    #remove duplicate entry
    if not user_rank_data :
         top_5_ranked = top_5_ranked[:5]
    else :
        top_5_ranked =  top_5_ranked[:6]
        if top_5_ranked[0][0] == username: # if the user is present at the first position
           user, score, rank = top_5_ranked[0]
           top_5_ranked[0] = (user, score, 1) # force rank to 1
    return top_5_ranked

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    session['start_time'] = time.time()
    session['current_qcm'] = 0
    session['paused_time'] = 0
    session['paused'] = False
    
    if 'level' not in session :
       return redirect(url_for('login'))
    level = session['level']
    
    if 'certificats' not in session:
        session['certificats'] = {}

    update_average_scores()
    
    print("Session username:", session.get('username'))  #LOG
    print("Session level:", session.get('level')) #LOG
    rankings = calculate_rankings(level)
    with open('module_structure.json', 'r', encoding='utf-8') as f:
         modules = json.load(f)
    if level not in modules:
        print(f"Error: Level '{level}' not found in module_structure.json") #LOG
        return "Level not found in module structure."

    semesters = modules[level]
    ranked_total_with_rank = []
    user_ranks = {}
    for index, (user, scores) in enumerate(rankings):
       ranked_total_with_rank.append((user, scores, index + 1))
       if user == username:
           user_ranks['total'] = index + 1
    
    for module, _ in session['certificats'].items():
         user_ranks[module]= get_user_rank(module, level)
        
    print(f"User ranks: {user_ranks}") #LOG
    print(f"Rankings total: {ranked_total_with_rank}") #LOG

    #Organize rankings by semester
    semester_rankings = organize_rankings_by_semester(level)

    #Get top rankings
    top_rankings = get_top_rankings(username, ranked_total_with_rank)
    
    return render_template('matiere.html',
       average_score_20 = session.get('certificats',{}),
       ranked_total = top_rankings,
       semesters = semesters,
       level = level,
       username=username,
       user_ranks = user_ranks,
       semester_rankings = semester_rankings
    )
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    session['start_time'] = time.time()
    session['current_qcm'] = 0
    session['paused_time'] = 0
    session['paused'] = False
    
    if 'level' not in session :
       return redirect(url_for('login'))
    level = session['level']
    
    if 'certificats' not in session:
        session['certificats'] = {}

    update_average_scores()
    
    print("Session username:", session.get('username'))  #LOG
    print("Session level:", session.get('level')) #LOG
    rankings = calculate_rankings(level)
    with open('module_structure.json', 'r', encoding='utf-8') as f:
         modules = json.load(f)
    if level not in modules:
        print(f"Error: Level '{level}' not found in module_structure.json") #LOG
        return "Level not found in module structure."

    semesters = modules[level]
    ranked_total_with_rank = []
    user_ranks = {}
    for index, (user, scores) in enumerate(rankings):
       ranked_total_with_rank.append((user, scores, index + 1))
       if user == username:
           user_ranks['total'] = index + 1
    
    for module, _ in session['certificats'].items():
         user_ranks[module]= get_user_rank(module, level)

    print(f"User ranks: {user_ranks}") #LOG
    print(f"Rankings total: {ranked_total_with_rank}") #LOG
    
    semester_rankings = organize_rankings_by_semester(level)

    return render_template('matiere.html',
       average_score_20 = session.get('certificats',{}),
       ranked_total = ranked_total_with_rank,
        semesters = semesters,
       level = level,
       username=username,
       user_ranks = user_ranks,
      semester_rankings = semester_rankings
    )
@app.route('/reset/<matiere>')
def reset_qcms(matiere):
  if 'username' not in session:
        return redirect(url_for('login'))
  username = session['username']
  
  if username not in MEMBERS: # add check
      return redirect(url_for('index')) # redirect if username does not exist

  qcms = load_qcms(matiere)
  MEMBERS[username][f'qcms_{matiere}'] = [qcm.to_dict() for qcm in qcms]

  session['current_qcm'] = 0
  update_average_scores()
  return redirect(url_for('qcm', matiere = matiere))


@app.route('/qcm/<matiere>', methods=['GET', 'POST'])
def qcm(matiere):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    current_qcm_index = session.get('current_qcm', 0)
    username = session['username']

    # Safet check: make sure that the user exists before accessing data
    if username not in MEMBERS:
         return redirect(url_for('index'))

    with open('module_structure.json', 'r', encoding='utf-8') as f:
         modules = json.load(f)
         semesters = modules[session['level']]
    
    # Retrieve QCM data, initialize if not exists
    qcms = MEMBERS.get(username, {}).get(f'qcms_{matiere}', [])
    if not qcms:
       qcms = [qcm.to_dict() for qcm in load_qcms(matiere)]
       if username in MEMBERS:
          MEMBERS[username][f'qcms_{matiere}'] = qcms
          save_members_data(MEMBERS) # Save updated user data
    
    qcms = [QCM.from_dict(data) for data in MEMBERS[username].get(f'qcms_{matiere}', [])]


    if not qcms:
       return redirect(url_for('index'))
    
    current_qcm = qcms[current_qcm_index]
    percentages = [1]
    show_percentages = False
    timer_qcm = "00:00"
    if request.method == 'POST':
        if 'pause' in request.form:
            if not session.get('paused', False) :
                session['last_pause'] = time.time()
                session['paused'] = True
            return redirect(url_for('qcm', matiere = matiere))

        if 'resume' in request.form:
            if session.get('paused', False) :
              session['paused_time'] = session.get('paused_time',0) + (time.time() - session['last_pause'])
              session['paused'] = False
            return redirect(url_for('qcm', matiere = matiere))

        if 'previous' in request.form:
            session['current_qcm'] = max(0, current_qcm_index - 1)
            session['disable_valider'] = False #reset the value of disabling
            return redirect(url_for('qcm', matiere = matiere))
        
        if 'voir' in request.form:
           percentages = collect_and_calculate_percentages(qcms,current_qcm_index, matiere, current_qcm.cours)
           if not session.get('paused', False) :
              elapsed_time = time.time() - session['start_time'] + session.get('paused_time', 0)
           else:
              elapsed_time = session.get('paused_time', 0)
           minutes, seconds = divmod(int(elapsed_time), 60)
           timer = f"{minutes:02}:{seconds:02}"
           timer_qcm = timer

           propositions_enumerate = list(zip(map(chr, range(65, 65 + len(current_qcm.propositions))), current_qcm.propositions))
            
           return render_template('qcm.html',
                                    qcm=current_qcm,
                                    timer=timer_qcm, # Utilisation du timer specifique au QCM
                                    current_qcm_index=current_qcm_index,
                                    total_qcms=len(qcms),
                                    qcm_done=current_qcm.done,
                                    propositions_enumerate = propositions_enumerate,
                                    start_time = session['start_time'],
                                    paused_time = session.get('paused_time', 0),
                                    paused = session.get('paused', False),
                                     average_score = current_qcm.calculate_moyenne(),
                                    global_success_rate= calculate_global_success_rate(qcms),
                                     percentages = percentages,
                                    show_percentages = True,
                                     timer_paused_at_validate= elapsed_time,
                                      validation_done=False,
                                    matiere = matiere,
                                     cours = current_qcm.cours,
                                    disable_valider = session.get('disable_valider',False) #check if button must be disabled
                                    )
        if 'valider' in request.form:
            selected = request.form.getlist('answers')
            selected = list(map(int, selected))
            # Récupération de la valeur `time_at_valide`
            time_at_valide = float(request.form.get('time_at_valide', 0) or 0)
            current_qcm.validate(selected)
            current_qcm.time_elapsed = time_at_valide
             # Update the  state of qcms in the MEMBERS array
            username = session['username']
            save_user_response(username, matiere, current_qcm.id, selected,  time_at_valide, current_qcm.cours)
            MEMBERS[username][f'qcms_{matiere}'] = [qcm.to_dict() for qcm in qcms]
            
            update_average_scores()
            save_members_data(MEMBERS)

            minutes, seconds = divmod(int(time_at_valide), 60)
            timer_qcm = f"{minutes:02}:{seconds:02}"

            propositions_enumerate = list(zip(map(chr, range(65, 65 + len(current_qcm.propositions))), current_qcm.positions))
            
            session['disable_valider'] = True  # disable button when page loads in next QCM

            return render_template('qcm.html',
                                    qcm=current_qcm,
                                    timer=timer_qcm, # Utilisation du timer specifique au QCM
                                    current_qcm_index=current_qcm_index,
                                    total_qcms=len(qcms),
                                    qcm_done=current_qcm.done,
                                    propositions_enumerate = propositions_enumerate,
                                    start_time = session['start_time'],
                                    paused_time = session.get('paused_time', 0),
                                    paused = session.get('paused', False),
                                     average_score = current_qcm.calculate_moyenne(),
                                    global_success_rate= calculate_global_success_rate(qcms),
                                     percentages = [],
                                    show_percentages = False,
                                    timer_paused_at_validate=time_at_valide,
                                      validation_done = True,
                                    matiere = matiere,
                                      cours = current_qcm.cours,
                                      disable_valider = session.get('disable_valider',False) #check if button must be disabled
                                    )

        if 'suivant' in request.form :
            if session['current_qcm'] +1 < len(qcms):
              session['current_qcm'] +=1
              session['start_time'] = time.time()
              session['paused_time'] = 0
              session['paused'] = False
            else :
              return redirect(url_for('fin', matiere = matiere))
            return redirect(url_for('qcm', matiere = matiere))

    if not session.get('paused', False) :
        elapsed_time = time.time() - session['start_time'] + session.get('paused_time', 0)
    else:
       elapsed_time = session.get('paused_time', 0)
    minutes, seconds = divmod(int(elapsed_time), 60)
    timer = f"{minutes:02}:{seconds:02}"
    
    # Ajout de la liste avec l'index dans app.py
    propositions_enumerate = list(zip(map(chr, range(65, 65 + len(current_qcm.propositions))), current_qcm.propositions))
    
    return render_template('qcm.html',
                           qcm=current_qcm,
                           timer=timer,
                           current_qcm_index=current_qcm_index,
                           total_qcms=len(qcms),
                           qcm_done=current_qcm.done,
                           propositions_enumerate = propositions_enumerate,
                           start_time = session['start_time'],
                           paused_time = session.get('paused_time', 0),
                           paused = session.get('paused', False),
                           percentages = [],
                           show_percentages = False,
                           average_score = current_qcm.calculate_moyenne(),
                           global_success_rate= calculate_global_success_rate(qcms),
                           timer_paused_at_validate=0,
                           validation_done = False,
                           matiere = matiere,
                           cours = current_qcm.cours,
                           disable_valider = session.get('disable_valider',False)
                           )

@app.route('/fin/<matiere>')
def fin(matiere):
    total_score = 0
    username = session['username']
    qcms = [QCM.from_dict(data) for data in MEMBERS[username].get(f'qcms_{matiere}',[])]
    total_elapsed_time = 0
    qcm_times = []
    for qcm in qcms:
       moyenne = qcm.calculate_moyenne()
       if moyenne is not None :
          total_score += moyenne
       total_elapsed_time += qcm.time_elapsed
       minutes, seconds = divmod(int(qcm.time_elapsed), 60)
       qcm_times.append(f"{minutes:02}:{seconds:02}")

    average_score = total_score / len(qcms) if qcms else 0
    
    update_average_scores()

    minutes, seconds = divmod(int(total_elapsed_time), 60)
    timer = f"{minutes:02}:{seconds:02}"
    return render_template('fin.html', qcms=qcms, average_score=average_score, timer=timer, qcm_times = qcm_times, matiere = matiere)



@app.route('/certificats')
def certificats():
   
   if 'username' not in session:
     return redirect(url_for('login'))
   return render_template('certificats.html',
     certificats = session.get('certificats',{})
    )
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('level', None)
    session.pop('certificats', None)
    session.pop('start_time', None)
    session.pop('current_qcm', None)
    session.pop('paused_time', None)
    session.pop('paused', None)
    return redirect(url_for('login'))
    
@app.route('/admin/login', methods=['GET', 'POST'], endpoint='admin_login')
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'Amourocma123': # Changed password here
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
             error = "Identifiants incorrects"
    return render_template('admin_login.html', error = error)

def is_admin_logged_in():
    return session.get('admin_logged_in', False)

@app.route('/admin/dashboard')
def admin_dashboard():
    global MEMBERS
    if not is_admin_logged_in():
        return redirect(url_for('admin_login'))
    
    search_term = request.args.get('search', '').lower()
    level_filter = request.args.get('level', 'all')
    sort_by = request.args.get('sort_by', 'username')
    sort_order = request.args.get('sort_order', 'asc')
    
    # Reload Members before filtering
    MEMBERS = load_members_data() #reload the members to get the right information
    
    filtered_members = {}
    for username, data in MEMBERS.items():
        if data.get('is_active', True) : #only show active members
          if level_filter == 'all' or data.get('level') == level_filter:
            if search_term in username.lower() or search_term in data.get('email', '').lower():
              filtered_members[username] = data
    
    # Sorting Logic
    def get_sort_key(item):
        username, data = item
        if sort_by == 'username':
            return username
        elif sort_by == 'email':
            return data.get('email', '')
        elif sort_by == 'level':
           return data.get('level', '')
        elif sort_by == 'password':
            return data.get('password', '')
        elif sort_by == 'registration_date':
            return datetime.strptime(data.get('registration_date', '01/01/1900'), '%d/%m/%Y')

    
    sorted_members = sorted(filtered_members.items(), key=get_sort_key, reverse=(sort_order == 'desc'))
    
    logged_in_users = defaultdict(int)
    for key in session.keys():
        if key != 'admin_logged_in' and key != "_permanent":
          logged_in_users[key] += 1
    total_members = len(MEMBERS)
    print("Total members found", total_members) #log
    return render_template('admin.html', 
                           members=dict(sorted_members),
                           logged_in_users = logged_in_users, 
                           search_term = search_term, 
                           level_filter = level_filter,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           total_members = total_members
                           )

@app.route('/admin/delete_member/<username>')
def delete_member(username):
    global MEMBERS
    if not is_admin_logged_in():
        return redirect(url_for('admin_login'))
    
    print(f"Attempting to delete member: {username}") # log
    
    try:
       with open(DATA_FILE, 'r') as f: #open and load the json file
          members_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error: could not load {DATA_FILE}")
        return redirect(url_for('admin_dashboard'))
    if username in members_data: # check if the user is in the dictionary
       print(f"User {username} found before deletion")
       del members_data[username] #delete the user from dictionary
       
       with open(DATA_FILE, 'w') as f: #save the modified dictionary
            json.dump(members_data, f, indent = 4)

       print(f"User {username} deleted from json file")
       MEMBERS = load_members_data() #reload `MEMBERS`
    else:
       print(f"User {username} not found in json file")
    
   
    print("MEMBERS after deletion:", len(MEMBERS), "members") #log
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_member', methods = ['GET', 'POST'])
def add_member():
        if not is_admin_logged_in():
            return redirect(url_for('admin_login'))
        if request.method == 'POST':
             username = request.form['username']
             password = request.form['password']
             email = request.form['email']
             level = request.form['level'] #getting level from form
             if username in MEMBERS:
               return render_template('add_member.html', error="Ce nom d'utilisateur existe déjà.")
             MEMBERS[username] = {'password': password, 'email': email, 'is_active': True, 'level' : level, 'certificats': {}}
             with open('module_structure.json', 'r', encoding='utf-8') as f:
               modules = json.load(f)
             if level in modules :
                semesters = modules[level]
                for semester, modules_list in semesters.items() :
                    for module in modules_list:
                        MEMBERS[username]['certificats'][module] = Certificat(module).to_dict()
                        MEMBERS[username][f'qcms_{module}'] = [qcm.to_dict() for qcm in load_qcms(module)]
             save_members_data(MEMBERS)
             return redirect(url_for('admin_dashboard'))
        return render_template('add_member.html')
@app.route('/admin/edit_member/<username>', methods=['GET', 'POST'])
def edit_member(username):
    if not is_admin_logged_in():
        return redirect(url_for('admin_login'))
    if username not in MEMBERS:
        return render_template('error.html', message='Member not found')

    if request.method == 'POST':
        password = request.form.get('password')
        email = request.form.get('email')
        level = request.form.get('level') # getting the level
        if password:
           MEMBERS[username]['password'] = password
        if email:
          MEMBERS[username]['email'] = email
        if level: #updating the level
            
            # Re-initialize qcms based on the level
            with open('module_structure.json', 'r', encoding='utf-8') as f:
               modules = json.load(f)
            if level in modules :
              semesters = modules[level]
              MEMBERS[username]['certificats'] = {}
              for semester, modules_list in semesters.items() :
                  for module in modules_list:
                    MEMBERS[username]['certificats'][module] = Certificat(module).to_dict()
                    MEMBERS[username][f'qcms_{module}'] = [qcm.to_dict() for qcm in load_qcms(module)]
            
            MEMBERS[username]['level'] = level
        save_members_data(MEMBERS)
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_member.html', member = MEMBERS[username], username=username)


# ---------------------- Warm Up Mechanism Removed-----------------------
# def warm_up_app():
#     while True:
#         try:
#             # Replace with your application's URL
#             url = "http://127.0.0.1:8080/"  # Use your actual application URL 
#             response = requests.get(url)
#             if response.status_code == 200:
#                 print("Warm-up request successful.")
#             else:
#                print(f"Warm-up request failed. Status Code: {response.status_code}")
#         except requests.exceptions.RequestException as e:
#             print(f"Error during warm-up request: {e}")
#         time.sleep(60 * 5) # Send a request every 5 minutes

# # Create warm-up thread
# warm_up_thread = threading.Thread(target=warm_up_app)
# warm_up_thread.daemon = True  # Ensure the thread exits when the app exits


if __name__ == '__main__':
    if not os.path.exists(RESPONSES_DIR):
        os.makedirs(RESPONSES_DIR)
    # Start the warm-up thread before running the app
   # warm_up_thread.start() # removed
    app.run(debug=True)