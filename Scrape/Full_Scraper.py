import json_pbp
import html_pbp
import espn_pbp
import json_shifts
import html_shifts
import playing_roster
import season_schedule
import pandas as pd
import shared
import time


# Holds list for broken games for shifts and pbp
broken_shifts_games = []
broken_pbp_games = []
players_missing_ids = []


def get_players_json(json):
    """
    Return dict of players for that game
    :param json: gameData section of json
    :return: dict of players->keys are the name (in uppercase)  
    """
    players = dict()

    players_json = json['players']
    for key in players_json.keys():
        name = shared.fix_name(players_json[key]['fullName'].upper())
        players[name] = {'id': ' '}
        try:
            players[name]['id'] = players_json[key]['id']
        except KeyError:
            print(name, ' is missing an ID number')
            players[name]['id'] = 'NA'

    return players


def combine_players_lists(json_players, roster_players):
    """
    Combine the json list of players (which contains id's) with the list in the roster html
    :param json_players: dict of all players with id's
    :param roster_players: dict with home and and away keys for players
    :return: dict containing home and away keys -> which contains list of info on each player
    """
    home_players = dict()
    for player in roster_players['Home']:
        try:
            name = shared.fix_name(player[2])
            id = json_players[name]['id']
            home_players[name] = {'id': id, 'number': player[0]}
        except KeyError:
            # This usually means it's the backup goalie (who didn't play) so it's no big deal with them
            if player[1] != 'G':
                players_missing_ids.extend([player])
                home_players[name] = {'id': 'NA', 'number': player[0]}

    away_players = dict()
    for player in roster_players['Away']:
        try:
            name = shared.fix_name(player[2])
            id = json_players[name]['id']
            away_players[name] = {'id': id, 'number': player[0]}
        except KeyError:
            if player[1] != 'G':
                players_missing_ids.extend([player])
                away_players[name] = {'id': 'NA', 'number': player[0]}

    return {'Home': home_players, 'Away': away_players}


def combine_html_json_pbp(json_df, html_df):
    """
    Join both data sources
    :param json_df: json pbp DataFrame
    :param html_df: html pbp DataFrame
    :return: finished pbp
    """
    columns = ['Game_Id', 'Date', 'Period', 'Event', 'Description', 'Time_Elapsed', 'Seconds_Elapsed', 'Strength',
               'Ev_Zone', 'Type', 'Ev_Team', 'Away_Team', 'Home_Team', 'p1_name', 'p1_ID', 'p2_name', 'p2_ID',
               'p3_name', 'p3_ID', 'awayPlayer1', 'awayPlayer1_id', 'awayPlayer2', 'awayPlayer2_id', 'awayPlayer3',
               'awayPlayer3_id', 'awayPlayer4', 'awayPlayer4_id', 'awayPlayer5', 'awayPlayer5_id', 'awayPlayer6',
               'awayPlayer6_id', 'homePlayer1', 'homePlayer1_id', 'homePlayer2', 'homePlayer2_id', 'homePlayer3',
               'homePlayer3_id', 'homePlayer4', 'homePlayer4_id', 'homePlayer5', 'homePlayer5_id', 'homePlayer6',
               'homePlayer6_id', 'Away_Goalie', 'Home_Goalie',  'Away_Skaters', 'Home_Skaters', 'Away_Score',
               'Home_Score', 'xC', 'yC']

    try:
        # Check if same amount of events...if not something is wrong
        if json_df.shape[0] != html_df.shape[0]:
            print('The Html and Json pbp for game {} are not the same'.format(json_df['Game_Id']))
            return None
        else:
            json_df = json_df.drop('Event', axis=1)       # Drop from json pbp
            game_df = pd.concat([html_df, json_df], axis=1)
            return pd.DataFrame(game_df, columns=columns)   # Make the columns in the order specified above
    except Exception:
        pass


def combine_espn_html_pbp(html_df, espn_df, game_id, date, away_team, home_team):
    """
    Merge the coordinate from the espn feed into the html DataFrame
    :param html_df: dataframe with info from html pbp
    :param espn_df: dataframe with info from espn pbp
    :param game_id: json game id
    :param date: ex: 2016-10-24
    :param away_team:
    :param home_team
    :return: merged DataFrame
    """
    columns = ['Game_Id', 'Date', 'Period', 'Event', 'Description', 'Time_Elapsed', 'Seconds_Elapsed', 'Strength',
               'Ev_Zone', 'Type', 'Ev_Team', 'Away_Team', 'Home_Team', 'p1_name', 'p1_ID', 'p2_name', 'p2_ID',
               'p3_name', 'p3_ID', 'awayPlayer1', 'awayPlayer1_id', 'awayPlayer2', 'awayPlayer2_id', 'awayPlayer3',
               'awayPlayer3_id', 'awayPlayer4', 'awayPlayer4_id', 'awayPlayer5', 'awayPlayer5_id', 'awayPlayer6',
               'awayPlayer6_id', 'homePlayer1', 'homePlayer1_id', 'homePlayer2', 'homePlayer2_id', 'homePlayer3',
               'homePlayer3_id', 'homePlayer4', 'homePlayer4_id', 'homePlayer5', 'homePlayer5_id', 'homePlayer6',
               'homePlayer6_id', 'Away_Goalie', 'Home_Goalie', 'Away_Skaters', 'Home_Skaters', 'Away_Score',
               'Home_Score', 'xC', 'yC']

    try:
        df = pd.merge(html_df, espn_df, left_on=['Period', 'Seconds_Elapsed', 'Event'],
                      right_on=['period', 'time_elapsed', 'event'], how='left')
        df = df.drop(['period', 'time_elapsed', 'event'], axis=1)
    except Exception as e:
        print('Error for combining espn and html pbp for game {}'.format(game_id), e)
        return None

    df['Game_Id'] = game_id
    df['Date'] = date
    df['Away_Team'] = away_team
    df['Home_Team'] = home_team

    return pd.DataFrame(df, columns=columns)


def scrape_pbp(game_id, date, roster):
    """
    Scrapes the pbp
    Automatically scrapes the json and html, if the json is empty the html picks up some of the slack and the espn
    xml is also scraped for coordinates
    :param game_id: json game id
    :param date: 
    :param roster: list of players in pre game roster
    :return: DataFrame with info or None if it fails
             dict of players with id's and numbers
    """
    game_json = json_pbp.get_pbp(game_id)

    try:
        teams = json_pbp.get_teams(game_json)                           # Get teams from json
        player_ids = get_players_json(game_json['gameData'])
        players = combine_players_lists(player_ids, roster['players'])  # Combine roster names with player id's
    except Exception as e:
        print('Problem with getting the teams or players', e)
        return None, None

    try:
        json_df = json_pbp.parse_json(game_json, game_id)
    except Exception as e:
        print('Error for Json pbp for game {}'.format(game_id), e)
        return None, None

    # Check if the json is missing the plays...if it is enable the HTML parsing to do more work to make up for the
    # json and scrape ESPN for the coordinates
    if len(game_json['liveData']['plays']['allPlays']) == 0:
        html_df = html_pbp.scrape_game(game_id, players, teams, False)
        espn_df = espn_pbp.scrape_game(date, teams['Home'], teams['Away'])
        game_df = combine_espn_html_pbp(html_df, espn_df, game_id, date, teams['Away'], teams['Home'])
    else:
        html_df = html_pbp.scrape_game(game_id, players, teams, True)
        game_df = combine_html_json_pbp(json_df, html_df)

    if game_df is not None:
        game_df['Home_Coach'] = roster['head_coaches']['Home']
        game_df['Away_Coach'] = roster['head_coaches']['Away']

    return game_df, players


def scrape_shifts(game_id, players):
    """
    Scrape the Shift charts (or TOI tables)
    :param game_id: json game id
    :param players: dict of players with numbers and id's
    :return: DataFrame with info or None if it fails
    """
    try:
        shifts_df = json_shifts.scrape_game(game_id)
    except Exception as e:
        print('Error for Json shifts for game {}'.format(game_id), e)
        try:
            shifts_df = html_shifts.scrape_game(game_id, players)
        except Exception as e:
                broken_shifts_games.extend([game_id])
                print('Error for html shifts for game {}'.format(game_id), e)
                return None

    return shifts_df


def scrape_game(game_id, date, if_scrape_shifts):
    """
    This scrapes the info for the game.
    The pbp is automatically scraped, and the whether or not to scrape the shifts is left up to the user
    :param game_id: game to scrap
    :param date: ex: 2016-10-24
    :param if_scrape_shifts: boolean, check if scrape shifts
    :return: DataFrame of pbp info
             (optional) Dataframe with shift info
    """
    shifts_df = None

    try:
        roster = playing_roster.scrape_roster(game_id)
    except Exception:
        return None, None     # Everything fails without the roster

    pbp_df, players = scrape_pbp(game_id, date, roster)

    if pbp_df is None:
        broken_pbp_games.extend([game_id])

    if if_scrape_shifts and pbp_df is not None:
        shifts_df = scrape_shifts(game_id, players)

    return pbp_df, shifts_df


def scrape_year(year, if_scrape_shifts):
    """
    Calls scrapeSchedule to get the game_id's to scrape and then calls scrapeGame and combines
    all the scraped games into one DataFrame
    :param year: year to scrape
    :param if_scrape_shifts: boolean, check if scrape shifts
    :return: nothing
    """
    schedule = season_schedule.scrape_schedule(year)
    season_pbp_df = pd.DataFrame()
    season_shifts_df = pd.DataFrame()

    i=0
    start = time.time()
    for game in schedule:
        print(game)
        i = i+1
        pbp_df, shifts_df = scrape_game(game[0], game[1], if_scrape_shifts)

        if pbp_df is not None:
            season_pbp_df = season_pbp_df.append(pbp_df)
        if shifts_df is not None:
            season_shifts_df = season_shifts_df.append(shifts_df)

        if i ==10:
            end = time.time()
            print((end - start) / 10)
            season_pbp_df.to_csv('nhl_pbp{}{}.csv'.format(year, int(year)+1), sep=',')
            if if_scrape_shifts:
                season_shifts_df.to_csv('nhl_shifts{}{}.csv'.format(year, int(year)+1), sep=',')


"""Test"""
scrape_year(2016, False)

print('Broken pbp:')
for x in broken_pbp_games:
    print(x)

print('Broken shifts:')
for x in broken_shifts_games:
    print(x)

print('Missing ids')
for x in players_missing_ids:
    print(x)




