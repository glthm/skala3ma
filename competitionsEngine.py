

import json
import os
import glob
import random
from datetime import datetime, date, timedelta
import time
import numpy as np
import pandas as pd
import numpy.random
from collections import Counter
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import plotly
import plotly.graph_objects as go
import plotly.express as px
import tracemalloc
import sqlite3 as lite
import uuid
import copy
from threading import RLock
import csv

import requests

import skala_db
import skala_journey

sql_lock = RLock()
from flask import Flask, redirect, url_for, session, request, render_template, send_file, jsonify, Response, \
    stream_with_context, copy_current_request_context

from functools import lru_cache, reduce
import logging
from dotenv import load_dotenv



load_dotenv()

DATA_DIRECTORY = os.getenv('DATA_DIRECTORY')
#PLAYLISTS_DB = DATA_DIRECTORY + "/db/playlists.sqlite"
COMPETITIONS_DB = DATA_DIRECTORY + "/db/competitions.sqlite"

# ID, date, name, location
COMPETITIONS_TABLE = "competitions"
# ID, name, club, m/f, list of climbs
USERS_TABLE = "climbers"
ROUTES_TABLE = "routes"
ROUTES_CLIMBED_TABLE = "routes_climbed"
GYM_TABLE = "gyms"
#comps = {}
#climbers = {}

emptyResults = {"M":{ "0":[], "1":[], "2":[]}, "F":{"0":[], "1":[], "2":[] }}

colors = { 'Vert':'#2E8B57',
'Vert marbré':'#2E8B57',
'Rouge':'#FF0000',
'Rouge marbré':'#FF0000',
'Gris':'#708090',
'Marron':'#A0522D',
'Rose marbré':'#FF69B4',
'Jaune':'#FFFF00',
'Orange':'#FFA500',
'Rose':'#FF69B4',
'Mauve':'#800080',
'Blanc':'#FFFFFF',
'Bleu':'#0000FF',
'Bleu marbré':'#0000FF',
'Noir':'#000000',
'Noir marbré':'#000000',
'Violet': '#9400D3',
'Saumon':'#FFE4C4'}


categories = {0:"Séniors 16-49 ans", 1:"Titane 50-69 ans", 2: "Diamant 70 ans et +"}

clubs = {               0:"APACHE" , 111:"Argenteuil Grimpe", 2:"AS Noiseraie Champy" , 3:"AS Pierrefitte" ,
                       4:"ASG Bagnolet"  , 5:"Athletic Club Bobigny", 6:"Au Pied du Mur (APDM)" ,
                       7:"Chelles Grimpe"  , 8:"Cimes 19"  , 9:"CMA Plein Air", 10:"CPS 10 - Faites le mur" ,
                       11:"Dahu 91" , 12:"Entente Sportive Aérospatial Mureaux(ESAM)" ,
                       1:"Entente Sportive de Nanterre"  ,14:"ESC 11", 15:"ESC XV"   ,16:"Espérance Sportive Stains",
                      17:"Grimpe 13"   ,18:"Grimpe Tremblay Dégaine", 19:"GrimpO6"   ,
                      20:"Groupe Escalade Saint Thibault"  ,
                      21:"Le Mur 20"  ,
                      22:"Neuf-a-pic", 23:"Quatre +"  ,24:"ROC 14"  , 25:"RSC Champigny",
                      26:"RSC Montreuillois"   ,27:"SNECMA Sports Corbeil", 28:"SNECMA Sports Genevilliers"   ,
                      29:"Union Sportive Saint Arnoult", 30:"US Fontenay"   , 31:"US Ivry" , 32:"US Métro"  ,
                      33:"USMA", 34:"Vertical 12", 35:"Vertical Maubuée", 36:"Villejuif Altitude" ,
                      37:"Autre club non répertorié"  }

# created - only visible to admin or someone who has the right to see it
# open - visible and registration is possible
# inprogress - visible, can still register and can enter routes climbed
# scoring - cannot register, can enter routes, calculate and see results
# closed - cannot change routes and no need to recalculate
competition_status_created = 0
competition_status_open = 1
competition_status_inprogress = 2
competition_status_scoring = 3
competition_status_closed = 4
competition_status_archived = 5
competition_status_future = 5

competition_status = {"created":competition_status_created, "open":1, "inprogress":2, "scoring":3, "closed":4, "archived":5}


user_roles = ["none", "judge", "competitor", "admin"]

supported_languages = {"en_US":"English","fr_FR":"Francais","pl_PL":"Polski"}

reference_data = {"categories":categories, "clubs":clubs, "competition_status": competition_status, "colors_fr":colors,
                  "supported_languages":supported_languages, "route_finish_status": skala_journey.route_finish_status}


# called from competitionsApp
def addCompetition(compId, name, date, routesid):
    if compId is None:
        compId = str(uuid.uuid4().hex)

    gym = skala_db.get_gym_by_routes_id(routesid)

    competition = {"id": compId, "name": name, "date": date, "gym": gym['name'],"gym_id":gym['id'],
                   "routesid": routesid, "status": "preopen", "climbers": {},
                   "results": copy.deepcopy(emptyResults)}
    # write this competition to db
    skala_db._add_competition(compId, competition);

    return compId


def update_competition_details(competition, name, date, routesid):
    competition['name']=name
    competition['date'] = date
    competition['routesid'] = routesid
    skala_db._update_competition(competition['id'], competition)


# add climber to a competition
def addClimber(climberId, competitionId, email, name, firstname, lastname, club, sex, category=0):
    logging.info("adding climber "+str(climberId))
    if email is None:
        raise ValueError('Email cannot be None')

    if climberId is None:
        climberId = str(uuid.uuid4().hex)

    try:
        category = int(category)
    except:
        raise ValueError('category must be an integer')

    if sex == 'm' or sex == 'M':
        sex = 'M'
    elif sex == 'f' or sex == 'F':
        sex = 'F'
    else:
        raise ValueError('Only valid values are mfMF')

    try:
        sql_lock.acquire()

        competition = get_competition(competitionId)
        climbers = competition['climbers']
        logging.info(climbers)

        for cid in climbers:
            if climbers[cid]['email']==email:
                #return climbers[cid]
                raise ValueError('User with email '+email+' already registered')

        climbers[climberId] = {"id":climberId, "email":email, "name":name, "firstname":firstname, "lastname":lastname,
                               "club" :club, "sex":sex, "category":category, "routesClimbed":[], "score":0, "rank":0 }
        logging.info(competition)

        _update_competition(competitionId, competition)
    finally:
        sql_lock.release()

    return climbers[climberId]


def get_climber_json(climberId, email, name, firstname, lastname, club, sex, category=0):
    climber_json = {"id": climberId, "email": email, "name": name, "firstname": firstname, "lastname": lastname,
                           "club": club, "sex": sex, "category": category, "routesClimbed": [], "score": 0, "rank": 0}



def getCompetitions():
    return get_all_competitions()


def getClimber(competitionId, climberId):
    comp = get_competition(competitionId)
    return comp['climbers'][climberId]


def getFlatCompetition(competitionId):
    print("retreiving competition" + str(competitionId))
    competition = get_competition(competitionId)

    for climberid in competition['climbers']:
        data = competition['climbers'][climberid]
        for i in range(100):
            if (i in competition['climbers'][climberid]['routesClimbed']):
                data['r' + str(i)] = 1
            else:
                data['r' + str(i)] = 0
    return competition


def getCompetition(competitionId):
    print("retreiving competition"+str(competitionId))
    return get_competition(competitionId)
    #return comps[competitionId]


def addRouteClimbed(competitionId, climberId, routeNumber):
    #print(comps)
    #comp = comps[competitionId]
    try:
        sql_lock.acquire()

        comp = get_competition(competitionId)
        climber = comp['climbers'][climberId]
        if climber is None:
            return

        routes_climbed = climber['routesClimbed']
        #print (routes_climbed)
        routes_climbed.append(routeNumber)
        _update_competition(competitionId, comp)
    finally:
        sql_lock.release()
    return comp


def setRoutesClimbed(competitionId, climberId, routeList):
    try:
        sql_lock.acquire()

        comp = get_competition(competitionId)

        climber = comp['climbers'][climberId]

        if climber is None:
            return
        climber['routesClimbed'] = []
        for route in routeList:
            routes_climbed = climber['routesClimbed']
            #print(routes_climbed)
            routes_climbed.append(route)
        comp = recalculate(competitionId, comp)
        _update_competition(competitionId, comp)
    finally:
        sql_lock.release()


def update_competition(competitionId, competition):
    _update_competition(competitionId, competition)


# calculates points per route per sex
# first loop counts how many times the route was climbed
# second loop iterates over this same list but then does 1000/times the route was climbed
def _getRouteRepeats(competitionId, sex, comp):
    pointsPerRoute = [0 for i in range(100)]
    for climber in comp['climbers']:
        if comp['climbers'][climber]['sex'] != sex:
            continue
        #print(climber)
        routesClimbed = comp['climbers'][climber]['routesClimbed']
        #print(routesClimbed)
        for r in routesClimbed:
            pointsPerRoute[r]=pointsPerRoute[r]+1

    #logging.info("route repeats: ")
    #logging.info(pointsPerRoute)

    for i, r in enumerate(pointsPerRoute):
        if r == 0 :
            pointsPerRoute[i]=1000
        else:
            pointsPerRoute[i]=1000/r
    #logging.info("points per route: ")
    #logging.info(pointsPerRoute)

    return pointsPerRoute



def recalculate(competitionId, comp=None):
    #logging.info('calculating...')

    try:
        sql_lock.acquire()
        if comp is None:
            comp = get_competition(competitionId)
            if comp is None:
                return
        comp['results'] = copy.deepcopy(emptyResults)
        for climberId in comp['climbers']:
            comp = _calculatePointsPerClimber(competitionId,climberId, comp)

        #rank climbers
        for climberId in comp['climbers']:
            try:
                climbersex = comp['climbers'][climberId]['sex']
                climbercat = str(comp['climbers'][climberId]['category'])

                comp['climbers'][climberId]['rank'] = comp['results'][climbersex][climbercat].index(comp['climbers'][climberId]['score'])+1
            except ValueError:
                comp['climbers'][climberId]['rank'] = -1

        results = comp['results']
        for sex in results:
            for cat in results[sex]:
                pointsA = results[sex][cat]
                if len(pointsA) == 0:
                    continue
                #pointsA.sort()
                #pointsA = results[sex][cat].sort()
                #results[sex][cat] = pointsA.sort()
        if comp is None:
            comp = _update_competition(competitionId, comp)
    finally:
        sql_lock.release()

    return comp


# returns sorted arrays based on rank
def get_sorted_rankings(competition):
    if competition['status'] not in [competition_status_closed,
                                     competition_status_scoring]:
        return None
    rankings = {}
    rankings['F'] = []
    rankings['M'] = []
    rankings['0F'] = []
    rankings['1F'] = []
    rankings['2F'] = []
    rankings['0M'] = []
    rankings['1M'] = []
    rankings['2M'] = []
    #rankings['club'] = []

    # scratch first
    for climberid in competition.get('climbers'):
        climber = competition.get('climbers').get(climberid)
        rank = int(climber['rank'])
        #rankings[climber['sex']].insert(rank-1, climber)

    # sort by awayPoints, then position; note the lambda uses a tuple
    a = competition.get('climbers').values()
    #clubs = set(competition.get('climbers')[k]['category'])

    clubs = reduce(lambda acc, c: acc.update({ competition['climbers'][c]['club'] :{"M":0, "F":0, "MC":0, "FC":0, "TOTAL":0 }})
                                        or acc if competition['climbers'][c]['club'] not in acc else acc,
                   competition.get('climbers'), {})

    #clubs = reduce(lambda acc, c: acc.append(competition['climbers'][c]['club'])
    #                              or acc if competition['climbers'][c]['club'] not in acc else acc,
    #               competition.get('climbers'), [])

    #clubs2 = set(clubs)

    #print(str(len(clubs)))
    #print(clubs)
    #b = a[0]
    for itemid in sorted(competition.get('climbers'),
                         key=lambda k: (competition.get('climbers')[k]['sex'], competition.get('climbers')[k]['score']),
                         reverse=True):
        climber = competition.get('climbers').get(itemid)
        rankings[climber['sex']].append(climber)

    for itemid in sorted(competition.get('climbers'),
                         key=lambda k: (competition.get('climbers')[k]['sex'], competition.get('climbers')[k]['category'], competition.get('climbers')[k]['score']),
                         reverse=True):
        climber = competition.get('climbers').get(itemid)
        catcode = str(climber['category'])+str(climber['sex'])
        rankings[catcode].append(climber)
        sex = climber['sex']
        classement = len(rankings[catcode])

        if climber['score']==0:
            continue
        # add one point for each climber
        points = clubs[climber['club']][sex]
        clubs[climber['club']][sex] = points + 1

        if classement<6:
            points = clubs[climber['club']][sex+"C"]
            clubs[climber['club']][sex+"C"] = points + 6 - classement


    for clubname in clubs:
        total = clubs[clubname]['M']+clubs[clubname]['F']+clubs[clubname]['MC']+clubs[clubname]['FC']
        clubs[clubname]['TOTAL'] = total

    sortedclubs = []
    prevTotal = -1
    #prevClub
    rank = 0
    for club in sorted(clubs, key=lambda x:(clubs[x]['TOTAL'], clubs[x]['F']+clubs[x]['M'], clubs[x]['F']),reverse=True):
        if club in ['other','Autre club non répertorié']:
            continue
        clubs[club]['name'] = club
        if prevTotal != clubs[club]['TOTAL']:
            rank = rank + 1
            prevTotal = clubs[club]['TOTAL']
        else:
            if clubs[club]['M'] == clubs[prevClub]['M']:
                if clubs[club]['F'] < clubs[prevClub]['F']:
                    rank = rank + 1
            else:
                rank = rank + 1

        clubs[club]['rank'] = rank
        sortedclubs.append(clubs[club])
        prevClub = club

    rankings['club']=sortedclubs
    return rankings



def _calculatePointsPerClimber(competitionId, climberId, comp):
    routesClimbed = comp['climbers'][climberId]['routesClimbed']
    sex = comp['climbers'][climberId]['sex']

    if sex == "M":
        routeRepeats = _getRouteRepeats(competitionId, "M", comp)
    elif sex == "F":
        routeRepeats = _getRouteRepeats(competitionId, "F", comp)
    else:
        return None;
    points = 0
    for i, v in enumerate(routesClimbed):
        points += routeRepeats[v]
        #logging.info(str(climberId) + " route="+str(v) + " - route points=" + str(routeRepeats[v]) + " total points=" + str(points))

    points = round(points)
    comp['climbers'][climberId]['score'] = points
    climbersex = comp['climbers'][climberId]['sex']
    climbercat = str(comp['climbers'][climberId]['category'])
    pointsA = comp['results'][climbersex][climbercat]
    pointsA.append(points)
    pointsA.sort(reverse=True)
    comp['climbers'][climberId]['rank'] = pointsA.index(points)
    #(comp['results'][climbersex][climbercat]).append(points)

    #logging.info("results " + str(climbersex)+str(climbercat)+ " add "+str(points))
    return comp


lru_cache.DEBUG = True


def init():
    logging.info('initializing competition engine...')

    skala_db.init()
    user_authenticated_fb("c1", "Bob Mob", "bob@mob.com",
                           "https://platform-lookaside.fbsbx.com/platform/profilepic/?asid=10224632176365169&height=50&width=50&ext=1648837065&hash=AeTqQus7FdgHfkpseKk")

    user_authenticated_fb("c1", "Bob Mob2", "bob@mob.com",
                           "https://platform-lookaside.fbsbx.com/platform/profilepic/?asid=10224632176365169&height=50&width=50&ext=1648837065&hash=AeTqQus7FdgHfkpseKk")

    user_authenticated_fb("c2", "Mary J", "mary@j.com",
                           "https://platform-lookaside.fbsbx.com/platform/profilepic/?asid=10224632176365169&height=50&width=50&ext=1648837065&hash=AeTqQus7FdgHfkpseKk")


    skala_journey.init()
    print('created ' + COMPETITIONS_DB)



#internal method.. not locked!!!
def _update_competition(compId, competition):

    if compId is None:
        raise ValueError("cannot update competition with None key");
    db = lite.connect(COMPETITIONS_DB)

    cursor = db.cursor()

    cursor.execute("update  " + COMPETITIONS_TABLE + " set jsondata=? where id=?  ",
                   [json.dumps(competition), compId])

    #logging.info('updated competition: '+str(compId))
    db.commit()
    db.close()


def delete_competition(compId):
    if compId is None:
        raise ValueError("cannot delete competition with None key");
    db = lite.connect(COMPETITIONS_DB)

    cursor = db.cursor()

    cursor.execute("delete from " + COMPETITIONS_TABLE + " where id=?  ",
                   [compId])

    db.commit()
    db.close()


def get_competition(compId):
    db = lite.connect(COMPETITIONS_DB)
    cursor = db.cursor()
    count = 0
    one = cursor.execute(
        '''SELECT jsondata FROM ''' + COMPETITIONS_TABLE + ''' where id=? LIMIT 1;''',[compId])
    one = one.fetchone()

    if one is None or one[0] is None:
        return None
    else:
        competition = json.loads(one[0])
        competition = _validate_or_upgrade_competition(competition)
        return competition


# this method is for migrating competitions to new format when available
def _validate_or_upgrade_competition(competition):

    needs_updating = False
    if competition.get('status') is None or competition.get('status') not in competition_status.values():
        needs_updating = True
        competition['status'] = competition_status['created']

    #if competition.get('gym_id') is None:
     #   raise ValueError('gym_id is missing for competition '+str(competition['id']))

    if needs_updating:
        update_competition(competition['id'], competition)

    return competition


def get_all_competitions():
    return skala_db.get_all_competitions()


def get_active_competitions():
    competitions = skala_db.get_all_competitions()
    #for key, competition in competitions.items:
     #   if competition.get('status')  in [competition_status_archived]:
      #       competitions.

    active_competitions = {key: competition for key,
                competition in competitions.items() if competition.get('status')  in [competition_status_archived]}

    return active_competitions


def get_user(id):
    return skala_db.get_user(id)


def get_user_by_email(email):
    return skala_db.get_user_by_email(email)


def get_all_user_emails():
    return skala_db.get_all_user_emails()


def get_all_competition_ids():
    return skala_db.get_all_competition_ids()


def user_self_update(climber, name, firstname, lastname, nick, sex, club, category):
    try:
        sql_lock.acquire()
        fullname = ""
        if firstname is not None and lastname is not None:
            fullname = firstname+" "+lastname
        newclimber = {'fullname': name, 'nick': nick, 'firstname':firstname, 'lastname':lastname,
                      'sex': sex, 'club': club, 'category': category}
        email = climber['email']
        db = lite.connect(COMPETITIONS_DB)
        cursor = db.cursor()
        if climber is None:
            skala_db._add_user(None, email, newclimber)
            logging.info('added user id ' + str(email))
        else:
            climber.update(newclimber)
            skala_db._update_user(climber['id'], email, climber)
            logging.info('updated user id ' + str(climber))
    finally:
        db.commit()
        db.close()
        sql_lock.release()
        logging.info("done with user:"+str(email))
        return climber


def upsert_user(user):
    try:
        sql_lock.acquire()
        existing_user = None
        email = user.get('email')
        db = lite.connect(COMPETITIONS_DB)
        cursor = db.cursor()

        if email is not None:
            existing_user = get_user_by_email(email)
            if existing_user is None:
                skala_db._add_user(None, email, user)
                logging.info('added user id ' + str(email))
            else:
                existing_user.update(user)
                skala_db._update_user(user['id'], email, existing_user)
    finally:
        db.commit()
        db.close()
        sql_lock.release()
        logging.info("upsert_user done with user:"+str(email))
        return existing_user


def user_authenticated_fb(fid, name, email, picture):
    try:
        sql_lock.acquire()
        user = get_user_by_email(email)
        _common_user_validation(user)
        db = lite.connect(COMPETITIONS_DB)
        cursor = db.cursor()
        if user is None:
            newuser = {'fid': fid, 'fname': name, 'email': email, 'fpictureurl': picture }
            skala_db._add_user(None, email, newuser)
            _common_user_validation(newuser)
            logging.info('added fb user id ' + str(email))
        else:
            u = {'fid': fid, 'fname': name, 'email': email, 'fpictureurl': picture}
            user.update(u)
            skala_db._update_user(user['id'], email, user)
            logging.info('updated user id ' + str(email))
    finally:
        db.commit()
        db.close()
        sql_lock.release()
        logging.info("done with user:"+str(email))


def user_authenticated_google(name, email, picture):
    try:
        sql_lock.acquire()
        user = get_user_by_email(email)
        _common_user_validation(user)
        db = lite.connect(COMPETITIONS_DB)
        cursor = db.cursor()
        if user is None:
            newuser = {'gname': name, 'email': email, 'gpictureurl': picture }
            _common_user_validation(newuser)
            skala_db._add_user(None, email, newuser)
            logging.info('added google user id ' + str(email))
        else:
            u = {'gname': name, 'email': email, 'gpictureurl': picture}
            user.update(u)
            skala_db._update_user(user['id'], email, user)
            logging.info('updated google user id ' + str(email))
    finally:
        db.commit()
        db.close()
        sql_lock.release()
        logging.info("done with user:"+str(email))


def _common_user_validation(user):
    if user is None:
        return

    permissions = user.get('permissions')
    if permissions is None:
        permissions = get_permissions(user)
        user['permissions'] = permissions


# returns base empty permissions dictionary
# who can create new competition? gym admins?
def get_permissions(user):
    if user is None:
        return _generate_permissions()

    if user.get('permissions') is None:
        user['permissions'] = _generate_permissions()

    if user.get('email') == 'dmossakowski@gmail.com':
        user['permissions']['godmode'] = True
        user['permissions']['general'] = ['create_competition', 'edit_competition', 'update_routes']
        user['permissions']['competitions'] = ['abc','def','ghi']
        user['permissions']['gyms'] = ['1']

    return user['permissions']


def _generate_permissions():
    return {
        "godmode": False,
        "general": [], # crud_competition crud_gym
        "users":[''],
        "competitions":['abc','def'], # everyone has ability to modify these test competitions
        "gyms":[] # contains gym ids
            }


def has_permission_for_competition(competitionId, user):
    permissions = get_permissions(user)
    huh = competitionId in permissions['competitions']
    return competitionId in permissions['competitions'] or session['name'] in ['David Mossakowski']


def add_user_permission_create_competition(user):
    skala_db.add_user_permission(user,'create_competition')


def add_user_permission_create_gym(user):
    skala_db.add_user_permission(user,'create_gym')


def has_permission_for_gym(gym_id, user):
    permissions = get_permissions(user)
    #huh = gym_id in permissions['gyms']
    return gym_id in permissions['gyms'] or session['name'] in ['David Mossakowski'] or permissions['godmode'] == 'true'


# modify permission to edit specific competition to a user
def modify_user_permissions_to_competition(user, competition_id, action="ADD"):
    return skala_db.modify_user_permissions_to_competition(user, competition_id, action)


def remove_user_permissions_to_competition(user, competition_id):
    return skala_db.modify_user_permissions_to_competition(user, competition_id, "REMOVE")


def add_user_permissions_to_gym(user, gym_id):
    return skala_db.modify_user_permissions_to_gym(user, gym_id, "ADD")


def remove_user_permissions_to_gym(user, gym_id):
    return skala_db.modify_user_permissions_to_gym(user, gym_id, "REMOVE")


def can_create_competition(climber):
    permissions = climber.get('permissions')
    if 'create_competition' in permissions['general']:
        return True
    return False
    #return climber is not None and climber['email'] in ['dmossakowski@gmail.com']


def can_edit_competition(climber, competition):
    permissions = climber.get('permissions')
    if 'edit_competition' in permissions['general']:
        return True
    return False
    #return climber is not None and climber['email'] in ['dmossakowski@gmail.com']


# can update routes if:
# user has update_routes general permission
# competition is in scoring or inprogress status
# user has permission for the given competition
def can_update_routes(user, competition):
    permissions = user.get('permissions')
    #if user['email in'] in ['dmossakowski@gmail.com']

    if 'update_routes' in permissions['general'] \
            and competition['status'] in [competition_status_scoring, competition_status_inprogress]\
            and competition['id'] in permissions['competitions']:
        return True

    return False


# checks if user can register for a competition
def can_register(user, competition):

    if competition is None:
        return '5055 - competition is null'

    if user is not None:
        climbers = competition['climbers']
        for cid in climbers:
            if climbers[cid]['email']==user['email']:
                return '5056 - User with email '+user['email']+' already registered'

    if len(competition['climbers']) > 150:
        return '5057 - Maximum registrations reached'

    # if anonymous registration and competition is in the correct state then allow
    if competition['status'] in [competition_status_open, competition_status_scoring, competition_status_inprogress]:
        return ""
    else:
        return '5057 - Competition status does not allow new registrations'


def can_edit_gym(user, gym):
    permissions = user.get('permissions')
    if gym['id'] in permissions['gyms'] or session['name'] in ['David Mossakowski']:
        return True
    return False
    #return climber is not None and climber['email'] in ['dmossakowski@gmail.com']


def can_create_gym(user):
    permissions = user.get('permissions')
    if 'create_gym' in permissions['general'] or session['name'] in ['David Mossakowski']:
        return True
    return False
    #return climber is not None and climber['email'] in ['dmossakowski@gmail.com']


# this overwrites details from competition registration to the main user entry
# these details will be used for next competition registration
# these details are deemed the most recent and correct
def user_registered_for_competition(climberId, name, firstname, lastname, email, sex, club, category):
    user = get_user_by_email(email)

    if climberId is None:
        climberId = str(uuid.uuid4().hex)

    newclimber = {}
    newclimber['id'] = climberId
    newclimber['name'] = name
    newclimber['firstname'] = firstname
    newclimber['lastname'] = lastname
    newclimber['sex'] = sex
    newclimber['club'] = club
    newclimber['category'] = category

    try:
        sql_lock.acquire()
        db = lite.connect(COMPETITIONS_DB)
        cursor = db.cursor()
        if user is None:
            _common_user_validation(newclimber)
            skala_db._add_user(climberId, email, newclimber)
            climber = newclimber
            logging.info('added user id ' + str(email))
        else:
            user.update(newclimber)
            skala_db._update_user(climberId, email, user)
            logging.info('updated user id ' + str(email))

    finally:
        db.commit()
        db.close()
        sql_lock.release()
        logging.info("done with user:"+str(name))
        #return climber


def update_gym_routes(gymid, routesid, jsondata):
    skala_db._update_gym_routes(gymid, routesid, jsondata)


def update_gym(gymid, jsondata):
    skala_db._update_gym(gymid, jsondata)


def update_routes(routesid, jsondata):
    skala_db._update_routes(routesid, jsondata)





def get_gym(gymid):
    gym = None
    try:
        sql_lock.acquire()
        gym = skala_db._get_gym(gymid)
    finally:
        sql_lock.release()
        logging.info("retrieved gym by id  "+str(gymid))
        return gym


def get_gyms():
    gyms = None
    try:
        sql_lock.acquire()
        gyms = skala_db._get_gyms()
    finally:
        sql_lock.release()
        logging.info("retrieved all gyms  ")
        return gyms




def get_routes(routesid):
    if routesid is None:
        # generate routes
        return generate_dummy_routes(100)
    else:
        routes = skala_db._get_routes(routesid)
        if type(routes) == list:
            routesdict = {"id":routesid, "routes":routes}
            skala_db._update_routes(routesid, routesdict)
            routes = routesdict
        return routes


def get_routes_by_gym_id(gym_id):
    return skala_db.get_routes_by_gym_id(gym_id)


def get_all_routes_ids():
    return skala_db.get_all_routes_ids()


def add_gym(user, gymid, routesid, name, logo_img_id=None, homepage=None, address=None, organization=None, routesA=None):
    if gymid is None:
        gymid = str(uuid.uuid4().hex)

    gymjson = get_gym_json(gymid, routesid, name, user['email'], logo_img_id, homepage, address, organization, routesA)

    skala_db._add_gym(gymid, routesid, gymjson)

    gym_permissions = user['permissions']['gyms']
    gym_permissions.append(gymid)
    skala_db.upsert_user(user)

    return gymjson


def delete_gym(gym_id):
    if gym_id is None:
        return
    try:
        sql_lock.acquire()
        skala_db._delete_gym(gym_id)
        skala_db._delete_routes_by_gymid(gym_id)
    finally:
        sql_lock.release()
        logging.info("deleted gym and routes for "+gym_id)


#routesid is the default routes to display
#routes array has ids of all routes belonging to this gym
def get_gym_json(gymid, routesid, name, added_by, logo_img_id, homepage, address, organization, routesA):
    gymjson = {'id': gymid, 'routesid': routesid, 'name': name,
               'logo_img_id': logo_img_id, 'homepage': homepage, 'address': address, 'organization': organization,
               'added_by': added_by, 'routes': routesA}
    return gymjson


def _get_route_dict(routeid, routenum, line, color1, color_modifier, grade, name, openedby, opendate, notes):
    oneline = {}
    oneline = {'id': routeid, 'routenum':routenum, 'line': line, 'colorfr': color1, 'color1': color1,
                'color_modifier': color_modifier, 'grade': grade, 'name': name, 'openedby': openedby,
                'opendate': opendate, 'notes': notes}
    return oneline


# replaces or adds routes depending if routesid is found
def upsert_routes(routesid, gym_id, routes):
    try:
        if routesid is None or routes is None:
            return None
        sql_lock.acquire()
        existing_routes = get_routes(routesid)
        db = lite.connect(COMPETITIONS_DB)
        cursor = db.cursor()

        logging.info("routes are a "+ str(type(routes)))

        if existing_routes is None:
            skala_db._add_routes(routesid, gym_id, routes)
            logging.info('routes added ' + str(routesid))
        else:
            skala_db._update_routes(routesid, routes)
            logging.info('routes updated ' + str(routesid))
    finally:
        db.commit()
        db.close()
        sql_lock.release()
        logging.info("done with routes :"+str(routesid))










def add_testing_data():
    addCompetition("abc", "FSGT 2021/2022", "20220101", "ESC 15")
    addCompetition("def", "FSGT 2021/2022", "20220207", "Tremblay")
    addCompetition("ghi", "FSGT 2021/2022", "20220312", "Roc 14")

    addClimber("c1", "abc", "c1@a.com", "Bob Mob", "Nanterre", "M")
    addClimber("c2", "abc", "c2@a.com", "Mary J", "Ville", "F")
    addClimber("c3", "abc", "c3@a.com", "Jean Li", "ESC15", "F")
    addClimber("c4", "abc", "c4@a.com", "Rose Rose", "Ville", "F")

    addClimber("c5", "abc", "c5@a.com", "Rudolf", "Nanterre", "M", 1)
    addClimber("c6", "abc", "c6@a.com", "Gary", "Ville", "m", 1)
    addClimber("c7", "abc", "c7@a.com", "Philomena", "ESC15", "F", 1)
    addClimber("c8", "abc", "c8@a.com", "Beatrice", "Ville", "F", 1)

    addClimber("c9", "abc", "c9@a.com", "Gianni", "Nanterre", "M", 2)
    addClimber("c10", "abc", "c10@a.com", "Monty", "Ville", "m", 2)
    addClimber("c11", "abc", "c11@a.com", "Rijka", "ESC15", "F", 2)
    addClimber("c12", "abc", "c12@a.com", "Salomona", "Ville", "F", 2)

    addClimber("c13", "abc", "c13@a.com", "Donny", "Nanterre", "M", 0)
    addClimber("c14", "abc", "c14@a.com", "Mark", "Ville", "m", 0)
    addClimber("c15", "abc", "c15@a.com", "Sonia", "ESC15", "F", 0)
    addClimber("c16", "abc", "c16@a.com", "Wilma", "Ville", "F", 0)

    setRoutesClimbed("abc", "c1", [2, 3, 4, 5, 7, 12, 17, 19, 24, 21, 24, 25, 26])
    addRouteClimbed("abc", "c1", 13)
    addRouteClimbed("abc", "c1", 14)
    addRouteClimbed("abc", "c1", 15)
    addRouteClimbed("abc", "c1", 16)

    setRoutesClimbed("abc", "c2", [2, 3, 4, 12, 13, 17, 24, 21, 24, 25, 26])
    setRoutesClimbed("abc", "c3", [1, 5, 6, 12, 13, 17,24, 25, 13, 15, 24])
    setRoutesClimbed("abc", "c4", [1, 13, 17, 24, 26, 52, 25, 34, 3, 4, 24])
    setRoutesClimbed("abc", "c5", [1, 13, 17, 14, 15, 16, 24, 25])
    setRoutesClimbed("abc", "c6", [1, 2, 3, 5, 7, 13, 14, 15, 15, 24, 25])
    setRoutesClimbed("abc", "c7", [1, 13, 14, 15, 16, 24, 25])
    setRoutesClimbed("abc", "c8", [2, 3, 12, 13, 14, 24, 25])

    setRoutesClimbed("abc", "c9", [2, 3, 12, 14, 24])
    setRoutesClimbed("abc", "c10", [2, 3, 4, 12, 13, 17, 18])
    setRoutesClimbed("abc", "c11", [2, 3, 4, 5, 12, 14, 24])
    setRoutesClimbed("abc", "c12", [2, 3, 4, 6, 4, 12])

    setRoutesClimbed("abc", "c13", [2, 3, 7, 8, 12, 15, 24])
    setRoutesClimbed("abc", "c14", [2, 3, 6, 7, 8, 12, 15, 17])
    setRoutesClimbed("abc", "c15", [2, 3, 4, 8, 12, 16, 17, 24])
    setRoutesClimbed("abc", "c16", [2, 3, 5, 12, 16, 17, 24])

    # competition def
    addClimber("c1", "def", "c1@a.com", "Bob Mob", "ESC15", "M")
    addClimber("c2", "def", "c2@a.com", "Ryan Pal", "Ville", "M")

    addClimber("c3", "def", "c3@a.com", "Jean Li", "ESC15", "F")
    addClimber("c4", "def", "c4@a.com", "Rose Rose", "Ville", "F")

    addClimber("c5", "def", "c5@a.com", "Rudolf", "Nanterre", "M", 1)
    addClimber("c6", "def", "c6@a.com", "Gary", "Ville", "m", 1)
    addClimber("c7", "def", "c7@a.com", "Philomena", "ESC15", "F", 1)
    addClimber("c8", "def", "c8@a.com", "Beatrice", "Ville", "F", 1)

    setRoutesClimbed("def", "c1", [1, 12, 24])
    setRoutesClimbed("def", "c2", [1, 12, 25])

    setRoutesClimbed("def", "c3", [1, 12, 24])
    setRoutesClimbed("def", "c4", [1 ,12, 25])

    setRoutesClimbed("def", "c5", [1, 12, 24])
    setRoutesClimbed("def", "c6", [1, 12, 25])

    setRoutesClimbed("def", "c7", [1, 12, 24])
    setRoutesClimbed("def", "c8", [1 ,12, 25])

    recalculate("abc")


def load_csv_routes():
    with open('topo-nanterre.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        routes = {'routes':[]}
        for row in reader:
             routes.get('routes').append(row)
    return routes


def loadgymsdict():
    return {'gyms': [
        {'id': '', 'routesid': '1', 'name': 'Nanterre Sprortiv' },
        {'id': '', 'routesid': '2', 'name': 'ESS 78'}]
    }


def generate_dummy_routes(size):
    routes_id = str(uuid.uuid4().hex)
    routes = {"id":routes_id }
    routesA = []
    for i in range(1, size):
        route_id = str(uuid.uuid4().hex)
        route = _get_route_dict(route_id, str(i), '1', '#2E8857', 'solid', '-', '', '', '', '')
        routesA.append(route)

    routes['routes'] = routesA
    routes['name'] = "Dummy routes"
    return routes


def get_img(img_id):
    return skala_db.get_image(img_id)


def loadroutesdict():
    return {'routes': [
        {'id': '', 'routenum': '1', 'line': '1', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '4b', 'name': 'Dummy route', 'openedby': '', 'opendate': '', 'notes': 'dummy routes'},
        {'id': '', 'routenum': '2', 'line': '1', 'colorfr': 'Rouge', 'color1': '#FF0000', 'color2': '', 'grade': '5a+', 'name': "L'égyptienne", 'openedby': 'Sebastiao', 'opendate': 'dec.-21', 'notes': 'Départ bas / horizontal'},
        {'id': '', 'routenum': '3', 'line': '1', 'colorfr': 'Gris', 'color1': '#708090', 'color2': '', 'grade': '5b+', 'name': 'Fifty shades of grès', 'openedby': 'Olivier', 'opendate': 'oct.-19', 'notes': 'sans arête'},
        {'id': '', 'routenum': '4', 'line': '1', 'colorfr': 'Marron', 'color1': '#A0522D', 'color2': '', 'grade': '5c', 'name': 'James Brown', 'openedby': 'Florian, Guillaume, Paulo', 'opendate': 'oct.-19', 'notes': ''},
        {'id': '', 'routenum': '5', 'line': '1', 'colorfr': 'Rose marbré', 'color1': '#FF69B4', 'color2': '', 'grade': '6b', 'name': 'Jeny dans le 6', 'openedby': 'Guillaume', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '6', 'line': '1', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '6a+', 'name': '', 'openedby': '', 'opendate': 'déc.-17', 'notes': ''},
        {'id': '', 'routenum': '7', 'line': '2', 'colorfr': 'Orange', 'color1': '#FFA500', 'color2': '', 'grade': '5a', 'name': "Jeanne d'Arc", 'openedby': 'Jeanne', 'opendate': 'avr.-19', 'notes': 'voie enfants'},
        {'id': '', 'routenum': '8', 'line': '2', 'colorfr': 'Rose', 'color1': '#FF69B4', 'color2': '', 'grade': '5a+', 'name': 'Spacy', 'openedby': 'Sebastiao', 'opendate': 'avr.-19', 'notes': ''},
        {'id': '', 'routenum': '9', 'line': '2', 'colorfr': 'Mauve', 'color1': '#800080', 'color2': '', 'grade': '5b', 'name': "L'araignée mauve", 'openedby': 'Pol', 'opendate': 'nov.-19', 'notes': ''},
        {'id': '', 'routenum': '10', 'line': '2', 'colorfr': 'Blanc', 'color1': '#FFFFFF', 'color2': '', 'grade': '6b', 'name': '', 'openedby': 'Franck', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '11', 'line': '2', 'colorfr': 'Bleu', 'color1': '#0000FF', 'color2': '', 'grade': '5c', 'name': 'Hématome', 'openedby': 'Aurélien, Guillaume', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '12', 'line': '2', 'colorfr': 'Gris', 'color1': '#708090', 'color2': '', 'grade': '5c', 'name': '', 'openedby': 'Nicolas', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '13', 'line': '3', 'colorfr': 'Rose marbré', 'color1': '#FF69B4', 'color2': '', 'grade': '4b', 'name': '', 'openedby': '', 'opendate': 'avr.-17', 'notes': ''},
        {'id': '', 'routenum': '14', 'line': '3', 'colorfr': 'Orange', 'color1': '#FFA500', 'color2': '', 'grade': '5a+', 'name': '', 'openedby': 'Sandrine, Sébastien', 'opendate': 'oct.-18', 'notes': ''},
        {'id': '', 'routenum': '15', 'line': '3', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '5c', 'name': 'Jaune Lennon', 'openedby': 'Olivier', 'opendate': 'oct.-19', 'notes': ''},
        {'id': '', 'routenum': '16', 'line': '3', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '6a', 'name': '', 'openedby': 'Hélène', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '17', 'line': '4', 'colorfr': 'Noir', 'color1': '#000000', 'color2': '', 'grade': '4a', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '18', 'line': '4', 'colorfr': 'Bleu', 'color1': '', 'color2': '', 'grade': '5b', 'name': 'Mousse bleue', 'openedby': 'Sebastiao', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '19', 'line': '4', 'colorfr': 'Blanc', 'color1': '', 'color2': '', 'grade': '6a', 'name': '', 'openedby': 'Franck', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '20', 'line': '4', 'colorfr': 'Rouge', 'color1': '', 'color2': '', 'grade': '5c', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '21', 'line': '4', 'colorfr': 'Orange', 'color1': '#FFA500', 'color2': '', 'grade': '6a', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '22', 'line': '5', 'colorfr': 'Orange', 'color1': '#FFA500', 'color2': '', 'grade': '6 ?', 'name': '', 'openedby': 'Jérôme', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '23', 'line': '5', 'colorfr': 'Noir marbré', 'color1': '', 'color2': '', 'grade': '4c', 'name': 'Marble bubble', 'openedby': 'Sebastiao', 'opendate': 'oct.-19', 'notes': ''},
        {'id': '', 'routenum': '24', 'line': '5', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '5a', 'name': 'Et toc', 'openedby': 'Jérôme', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '25', 'line': '5', 'colorfr': 'Bleu', 'color1': '', 'color2': '', 'grade': '5c', 'name': 'La bleusaille', 'openedby': 'Sebastiao', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '26', 'line': '5', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '5c', 'name': "C'est vert", 'openedby': 'Olivier', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '27', 'line': '5', 'colorfr': 'Gris', 'color1': '#708090', 'color2': '', 'grade': '5c+', 'name': 'La base', 'openedby': 'Jérôme', 'opendate': 'avr.-17', 'notes': ''},
        {'id': '', 'routenum': '28', 'line': '5', 'colorfr': 'Rose', 'color1': '#FF69B4', 'color2': '', 'grade': '5c', 'name': 'Pollux', 'openedby': 'Ivan', 'opendate': 'nov.-19', 'notes': 'sans arête'},
        {'id': '', 'routenum': '29', 'line': '5', 'colorfr': 'Orange', 'color1': '', 'color2': '', 'grade': '6a', 'name': 'Peace mémé', 'openedby': 'Jérôme', 'opendate': '', 'notes': 'sans arête'},
        {'id': '', 'routenum': '30', 'line': '5', 'colorfr': 'Vert marbré', 'color1': '#2E8B57', 'color2': '', 'grade': '6a+/6b ?', 'name': '', 'openedby': 'Estelle', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '31', 'line': '6', 'colorfr': 'Rose marbré', 'color1': '#FF69B4', 'color2': '', 'grade': '6b', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '32', 'line': '7', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '4c', 'name': 'Début de séance', 'openedby': 'Rémy', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '33', 'line': '7', 'colorfr': 'Bleu marbré', 'color1': '', 'color2': '', 'grade': '5b', 'name': '', 'openedby': '', 'opendate': 'juil.-18', 'notes': ''},
        {'id': '', 'routenum': '34', 'line': '7', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '5c+', 'name': 'La coulée verte', 'openedby': 'Sebastien, Yohan', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '35', 'line': '8', 'colorfr': 'Rouge marbré', 'color1': '', 'color2': '', 'grade': '6a', 'name': 'Timal', 'openedby': 'Jérôme', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '36', 'line': '8', 'colorfr': 'Orange', 'color1': '', 'color2': '', 'grade': '6c+', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '37', 'line': '8', 'colorfr': 'Rose marbré', 'color1': '', 'color2': '', 'grade': '7b', 'name': '', 'openedby': '', 'opendate': '', 'notes': 'suite de la voie en 6'},
        {'id': '', 'routenum': '38', 'line': '9', 'colorfr': 'Noir', 'color1': '', 'color2': '', 'grade': '5a+', 'name': '', 'openedby': '', 'opendate': 'oct.-18', 'notes': ''},
        {'id': '', 'routenum': '39', 'line': '9', 'colorfr': 'Bleu', 'color1': '', 'color2': '', 'grade': '5c', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '40', 'line': '9', 'colorfr': 'Gris', 'color1': '#708090', 'color2': '', 'grade': '6a+', 'name': 'Cour-âge', 'openedby': 'Jérôme', 'opendate': 'avr.-19', 'notes': 'dièdre'},
        {'id': '', 'routenum': '41', 'line': '9', 'colorfr': 'Rouge', 'color1': '', 'color2': '', 'grade': '6b', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '42', 'line': '9', 'colorfr': 'Blanc', 'color1': '', 'color2': '', 'grade': '6c/7a ?', 'name': '', 'openedby': 'Franck', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '43', 'line': '10', 'colorfr': 'Violet', 'color1': '', 'color2': '', 'grade': '5a', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '44', 'line': '10', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '5b+', 'name': '', 'openedby': 'Jennifer', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '45', 'line': '10', 'colorfr': 'Vert', 'color1': '', 'color2': '', 'grade': '6a ?', 'name': '', 'openedby': 'Franck', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '46', 'line': '11', 'colorfr': 'Rouge', 'color1': '', 'color2': '', 'grade': '6c', 'name': "Au nom de l'amour", 'openedby': 'Jérôme', 'opendate': 'oct.-19', 'notes': ''},
        {'id': '', 'routenum': '47', 'line': '11', 'colorfr': 'Noir marbré', 'color1': '', 'color2': '', 'grade': '7b', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '48', 'line': '12', 'colorfr': 'Rose marbré', 'color1': '', 'color2': '', 'grade': '5c', 'name': '', 'openedby': 'Jérôme', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '49', 'line': '12', 'colorfr': 'Orange', 'color1': '#FFA500', 'color2': '', 'grade': '6a', 'name': 'Pozer', 'openedby': 'Jérôme', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '50', 'line': '12', 'colorfr': 'Mauve', 'color1': '', 'color2': '', 'grade': '6c', 'name': 'Carma-sutra', 'openedby': 'Jérôme', 'opendate': 'fév-19', 'notes': ''},
        {'id': '', 'routenum': '51', 'line': '12', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '6c+', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '52', 'line': '12', 'colorfr': 'Bleu', 'color1': '', 'color2': '', 'grade': '7b', 'name': 'Serrerbrale', 'openedby': 'Jérôme', 'opendate': 'nov.-19', 'notes': ''},
        {'id': '', 'routenum': '53', 'line': '12', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '7b', 'name': '', 'openedby': '', 'opendate': 'déc.-17', 'notes': ''},
        {'id': '', 'routenum': '54', 'line': '12', 'colorfr': 'Blanc', 'color1': '', 'color2': '', 'grade': '8a ?', 'name': '', 'openedby': 'Jérôme', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '55', 'line': '13', 'colorfr': 'Noir', 'color1': '', 'color2': '', 'grade': '5b', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '56', 'line': '13', 'colorfr': 'Bleu', 'color1': '', 'color2': '', 'grade': '6c', 'name': '', 'openedby': 'Franck', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '57', 'line': '13', 'colorfr': 'Rouge', 'color1': '', 'color2': '', 'grade': '6c', 'name': '', 'openedby': 'Jérôme', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '58', 'line': '13', 'colorfr': 'Rose', 'color1': '', 'color2': '', 'grade': '6c', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '59', 'line': '14', 'colorfr': 'Orange', 'color1': '#FFA500', 'color2': '', 'grade': '5a', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '60', 'line': '14', 'colorfr': 'Marron', 'color1': '', 'color2': '', 'grade': '6a', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '61', 'line': '14', 'colorfr': 'Vert marbré', 'color1': '#2E8B57', 'color2': '', 'grade': '6b+', 'name': '', 'openedby': 'Franck', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '62', 'line': '15', 'colorfr': 'Rouge', 'color1': '', 'color2': '', 'grade': '6a', 'name': 'Doigt döner', 'openedby': 'Olivier, Rémy', 'opendate': 'avr.-19', 'notes': ''},
        {'id': '', 'routenum': '63', 'line': '15', 'colorfr': 'Rose marbré', 'color1': '', 'color2': '', 'grade': '6a', 'name': '', 'openedby': 'Franck', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '64', 'line': '15', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '6a+', 'name': 'Rire jaune', 'openedby': 'Aurélien, Guillaume', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '65', 'line': '15', 'colorfr': 'Noir marbré', 'color1': '', 'color2': '', 'grade': '7a ?', 'name': '', 'openedby': 'Jérôme', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '66', 'line': '15', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '6c', 'name': '', 'openedby': 'Franck', 'opendate': 'déc.-17', 'notes': ''},
        {'id': '', 'routenum': '67', 'line': '15', 'colorfr': 'Blanc', 'color1': '', 'color2': '', 'grade': '7a+', 'name': '', 'openedby': 'Franck', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '68', 'line': '16', 'colorfr': 'Orange', 'color1': '', 'color2': '', 'grade': '5b', 'name': '', 'openedby': 'Franck', 'opendate': 'oct.-18', 'notes': ''},
        {'id': '', 'routenum': '69', 'line': '16', 'colorfr': 'Rose', 'color1': '', 'color2': '', 'grade': '5c+', 'name': '', 'openedby': 'Franck', 'opendate': 'fev-22', 'notes': ''},
        {'id': '', 'routenum': '70', 'line': '16', 'colorfr': 'Rouge', 'color1': '', 'color2': '', 'grade': '6a', 'name': '', 'openedby': 'Franck', 'opendate': 'fev-22', 'notes': 'départ commun 5c en 17'},
        {'id': '', 'routenum': '71', 'line': '16', 'colorfr': 'Bleu marbré', 'color1': '', 'color2': '', 'grade': '6b', 'name': '', 'openedby': 'Franck', 'opendate': 'oct.-18', 'notes': ''},
        {'id': '', 'routenum': '72', 'line': '16', 'colorfr': 'Gris', 'color1': '', 'color2': '', 'grade': '6b', 'name': 'Pince-mi pince-la', 'openedby': 'Jérôme', 'opendate': 'dec.-21', 'notes': 'colonnettes'},
        {'id': '', 'routenum': '73', 'line': '17', 'colorfr': 'Rouge', 'color1': '', 'color2': '', 'grade': '5c', 'name': '', 'openedby': 'Franck', 'opendate': 'fev-22', 'notes': 'départ commun 6a en 16'},
        {'id': '', 'routenum': '74', 'line': '17', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '5a', 'name': 'Joker', 'openedby': 'Eftalya, Sebastiao', 'opendate': 'nov.-19', 'notes': ''},
        {'id': '', 'routenum': '75', 'line': '17', 'colorfr': 'Saumon', 'color1': '#FFE4C4', 'color2': '', 'grade': '5a', 'name': 'Dièdre or alive', 'openedby': 'Jennifer', 'opendate': 'oct.-19', 'notes': ''},
        {'id': '', 'routenum': '76', 'line': '18', 'colorfr': 'Jaune', 'color1': '#FFFF00', 'color2': '', 'grade': '5c', 'name': 'Jauniligne', 'openedby': 'Sebastiao', 'opendate': 'oct.-19', 'notes': ''},
        {'id': '', 'routenum': '77', 'line': '18', 'colorfr': 'Blanc', 'color1': '', 'color2': '', 'grade': '6a+ ?', 'name': '', 'openedby': 'Davidski', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '78', 'line': '18', 'colorfr': 'Orange', 'color1': '', 'color2': '', 'grade': '5c', 'name': '', 'openedby': 'Franck', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '79', 'line': '18', 'colorfr': 'Bleu marbré', 'color1': '', 'color2': '', 'grade': '6c', 'name': '', 'openedby': 'Franck', 'opendate': 'oct.-18', 'notes': 'sans colonnettes'},
        {'id': '', 'routenum': '80', 'line': '19', 'colorfr': 'Saumon', 'color1': '', 'color2': '', 'grade': '5a+', 'name': '', 'openedby': '', 'opendate': 'juin-18', 'notes': ''},
        {'id': '', 'routenum': '81', 'line': '19', 'colorfr': 'Bleu', 'color1': '', 'color2': '', 'grade': '5b+', 'name': 'La coincée', 'openedby': 'Jérôme', 'opendate': 'déc.-19', 'notes': ''},
        {'id': '', 'routenum': '82', 'line': '19', 'colorfr': 'Noir', 'color1': '', 'color2': '', 'grade': '5b+', 'name': 'Icosium', 'openedby': 'Djallel', 'opendate': 'oct.-18', 'notes': ''},
        {'id': '', 'routenum': '83', 'line': '19', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '6a+', 'name': '', 'openedby': 'Franck', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '84', 'line': '20', 'colorfr': 'Vert', 'color1': '#2E8B57', 'color2': '', 'grade': '4c', 'name': '', 'openedby': '', 'opendate': 'juin-18', 'notes': ''},
        {'id': '', 'routenum': '85', 'line': '20', 'colorfr': 'Gris', 'color1': '', 'color2': '', 'grade': '5c ?', 'name': '', 'openedby': 'Nicolas', 'opendate': 'dec.-21', 'notes': ''},
        {'id': '', 'routenum': '86', 'line': '20', 'colorfr': 'Bleu', 'color1': '', 'color2': '', 'grade': '5b+', 'name': 'Clean up', 'openedby': 'Jérôme', 'opendate': 'déc.-19', 'notes': ''},
        {'id': '', 'routenum': '87', 'line': '20', 'colorfr': 'Jaune', 'color1': '', 'color2': '', 'grade': '5b+', 'name': '', 'openedby': '', 'opendate': '', 'notes': ''},
        {'id': '', 'routenum': '88', 'line': '20', 'colorfr': 'Marron', 'color1': '', 'color2': '', 'grade': '5c', 'name': '', 'openedby': 'Alex', 'opendate': 'fev-22', 'notes': 'sans vire, prises uniquement'},
        {'id': '', 'routenum': '89', 'line': '20', 'colorfr': 'Orange', 'color1': '', 'color2': '', 'grade': '6b', 'name': '', 'openedby': 'Franck', 'opendate': '', 'notes': ''}]}

if __name__ == '__main__':

    init()


    #library = loadLibraryFromFiles()

    #getOrphanedTracks(library)


