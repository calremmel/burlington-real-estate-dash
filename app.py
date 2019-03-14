import os

import dash
import dash_core_components as dcc
import dash_html_components as html
import dash_table
from dash.dependencies import Input, Output, State
from dash_table.Format import Format, Scheme, Sign, Symbol
import dash_table.FormatTemplate as FormatTemplate
import pandas as pd
import plotly.graph_objs as go
import re
import json
import urllib
import urllib.parse

from functools import reduce

mapbox_access_token = 'pk.eyJ1IjoiY2FscmVtbWVsIiwiYSI6ImNqc25scWtiMzBkcGI0M3BtNDRrbnFvNGoifQ.qmi7OtQn6vIJbHbbTZs2MQ'

# Define format for table columns, including currency formatting.
TABLE_COLS = ["Parcel ID", "Address", "Property Value", "Listed Owner", "Principals"]
FORMAT_COLS = [{"name": i, "id": i} for i in TABLE_COLS]
FORMAT_COLS[2]['type'] = 'numeric'
FORMAT_COLS[2]['format'] = FormatTemplate.money(0)

# Load data.
geocodes = pd.read_csv('data/csvs/geocoded_properties.csv')
principals = pd.read_csv('data/csvs/props_to_principals.csv')

# Define color list for city wards.
colors = ["rgba(251,180,174,0.5)", "rgba(179,205,227,0.5)", "rgba(204,235,197,0.5)", "rgba(222,203,228,0.5)", "rgba(254,217,166,0.5)", "rgba(255,255,204,0.5)", "rgba(229,216,189,0.5)", "rgba(253,218,236,0.5)"]
# GeoJSON files for city wards.
files = ['ward1.json', 'ward2.json', 'ward3.json', 'ward4.json', 'ward5.json', 'ward6.json', 'ward7.json', 'ward8.json']

all_wards = ['Ward 1', 'Ward 2', 'Ward 3', 'Ward 4', 'Ward 5', 'Ward 6', 'Ward 7', 'Ward 8']

# load GeoJSON layers for map
layers_one = []
for i, name in enumerate(files):
    layers_one.append(
        dict(
            sourcetype = 'geojson',
            source = json.load(open("data/wards/" + name)),
            type = 'fill',
            color = colors[i],
            below="road_major_label"
        )
    )

app = dash.Dash(__name__)

server = app.server

app.layout = html.Div(children=[
    html.H1(children='Who Owns Burlington?'),

    html.Div(children=[
        html.H3('Enter Last Name(s):'),
        html.P('Separate names by commas.'),
        dcc.Input(id='my-id', value='handy, bissonette, pomerleau', type='text')]),
        
    html.Div(children=[
        
        html.H3('Filter by Ward:'),
        dcc.Dropdown(
            id='ward-select',
            options=[
                {'label': 'Ward 1', 'value': 'Ward 1'},
                {'label': 'Ward 2', 'value': 'Ward 2'},
                {'label': 'Ward 3', 'value': 'Ward 3'},
                {'label': 'Ward 4', 'value': 'Ward 4'},
                {'label': 'Ward 5', 'value': 'Ward 5'},
                {'label': 'Ward 6', 'value': 'Ward 6'},
                {'label': 'Ward 7', 'value': 'Ward 7'},
                {'label': 'Ward 8', 'value': 'Ward 8'},
        ],
        value=None,
        multi=True
        )
    ]),
    
    html.Div(children=[

        dcc.Graph(
            id ='map'
        )

    ]),

    html.Div(children=[

        dcc.Graph(
            id ='ward-bars'
        )

    ]),

    html.A(
        'Download Data',
        id='download-link',
        download="rawdata.csv",
        href="",
        target="_blank"
    ),

    html.Div(children=[
        dash_table.DataTable(
            id='table',
            columns = FORMAT_COLS,
            sorting=True
            )
    ])
])

@app.callback(
    Output('download-link', 'href'),
    [Input('my-id', 'n_submit'), Input('ward-select', 'value')],
    [State('my-id', 'value')])
def update_download_link(ns, ward_list, name_string):
    dff = generate_table(ward_list, name_string)
    csv_string = dff.to_csv(index=False, encoding='utf-8')
    csv_string = "data:text/csv;charset=utf-8," + urllib.parse.quote(csv_string)
    return csv_string

@app.callback(
    Output('ward-bars', 'figure'),
    [Input('my-id', 'n_submit'), Input('ward-select', 'value')],
    [State('my-id', 'value')])
def update_bars(ns, ward_list, name_string):

    if ward_list == None:
        ward_list = all_wards

    if name_string == "":
        traces = [go.Bar(x=ward_list, y=[0 for ward in ward_list])]
    else:
        name_list = name_lister(name_string)
        traces = []

        for name in name_list:
            ward_counts = get_ward_counts(name, ward_list)
            trace = go.Bar(
                x=ward_list,
                y=ward_counts,
                name=name.title()
            )
            traces.append(trace)
    return {
        'data': traces
    }

@app.callback(
    Output('map', 'figure'),
    [Input('my-id', 'n_submit'), Input('ward-select', 'value')],
    [State('my-id', 'value')])
def update_map(ns, ward_list, name_string):
    
    marker_colors = ['rgb(215,25,28)','rgb(253,174,97)','rgb(255,255,191)','rgb(171,217,233)','rgb(44,123,182)']

    if name_string == "":
        traces = [go.Scattermapbox()]
    else:
        name_list = name_lister(name_string)

        traces = []

        for i, name in enumerate(name_list):

            lats, lngs, text = get_marker_data(name, ward_list)

            trace = go.Scattermapbox(
                lat=lats,
                lon=lngs,
                mode='markers',
                marker=dict(
                    size=8
                    # color=marker_colors[i]
                ),
                text=text,
                name=name.title()
            )
            

            traces.append(trace)

    return {
        'data': traces,
        'layout': go.Layout(
            height=800,
            autosize=True,
            hovermode='closest',
            mapbox=dict(
                accesstoken=mapbox_access_token,
                bearing=0,
                center=dict(
                    lat=44.495,
                    lon=-73.23
                ),
                pitch=0,
                zoom=11.45,
                layers = layers_one
            )
        )
    }

def generate_table(ward_list, name_string):
    if name_string == '':
        empty_df = pd.DataFrame()
        return empty_df
    
    name_list = []

    if "," not in name_string:
        name_list.append(name_string)
    else:
        name_split = name_string.split(",")
        name_list = [x.strip() for x in name_split]
    
    df_list = []

    for name in name_list:
        df=name_search(name)
        df_list.append(df)

    if len(df_list) == 1:
        combined_df = df_list[0]

    else:
        combined_df = pd.concat(df_list)

    final_df = pd.merge(combined_df, geocodes, how='left', left_on='property_id', right_on='Parcel ID')
    
    if ward_list:
        ward_arrays = [final_df[x] for x in ward_list]
        ward_bool = reduce((lambda x, y: x | y), ward_arrays)
        final_df = final_df[ward_bool]
    
    final_df = final_df[["property_id", "Address", "property_real_value", "owner_name", "principals"]]
    cols = ["Parcel ID", "Address", "Property Value", "Listed Owner", "Principals"]
    final_df.columns = cols
    final_df["Listed Owner"] = final_df["Listed Owner"].str.title()
    final_df["Principals"] = final_df["Principals"].str.title()
    return final_df

@app.callback(
    Output('table', 'data'),
    [Input('my-id', 'n_submit'), Input('ward-select', 'value')],
    [State('my-id', 'value')])
def update_table(ns, ward_list, name_string):
    final_df = generate_table(ward_list, name_string)
    return final_df.to_dict("rows")

def findWholeWord(word, sentence):
    """Finds a complete word in a sentence.

    Args:
        word (str): Word to be searched for.
        sentence (str): Sentence to be searched.
    
    Returns:
        bool: True if found, False otherwise.
    """
    result = re.compile(r'\b({0})\b'.format(word), flags=re.IGNORECASE).search(sentence)
    if result:
        return True
    else:
        return False

def currency(number):
    '''Formats integer or float as currency.'''
    return '${:,.2f}'.format(number)

def principal_string(id, df=principals):
    """Returns a string of principal names, separated by commas.

    Args:
        id (str): Property id to be matched.
        df (DataFrame): Dataframe to be searched.
    
    Returns:
        str: Comma separated principal names.
    """
    df=df

    prin_series = df.loc[df['property_id'] == id, 'principals']
    prin_list = sorted(list(prin_series.unique()))
    prin_string = ", ".join(prin_list)

    return prin_string

def name_search(name, df=principals, institutions=False):
    """Finds properties associated with a name.

    Args:
        name (str): Name to be searched for.
        df (DataFrame): DataFrame to be searched.
        institutions (bool): Include major gov institutions only if True.
    
    Returns:
        data (DataFrame): Properties that match name.
    """
    df=df
    name=name.upper()
    
    inst_lst = [45152.0, 43409.0, 46484.0, 46891.0]
    
    principal_bool = df.principals.map(lambda x: findWholeWord(name, x))
    owner_bool = df.owner_name.map(lambda x: findWholeWord(name, x))
    
    data = df[
        principal_bool | owner_bool
    ].sort_values(
        ['property_id', 'owner_name', 'principals']
    ).drop_duplicates(subset=['property_id'])
    
    if institutions == False:
        data = data[data['business_id'].isin(inst_lst) == False]
    
    data['principals'] = data['property_id'].map(principal_string)

    return data

def get_marker_data(name, ward_list):
    """Returns makers for properties associated with name.

    Args:
        name (str): Name to be searched for.
        ward_list (list): List of city wards to filter by.
    
    Returns:
        lats (Series): Series of latitudes.
        lngs (Series): Series of longitudes.
        text (Series): Series of strings with addresses, owners, values.
    """
    df = name_search(name)
    data = pd.merge(df, geocodes, how='left', left_on='property_id', right_on='Parcel ID')

    if ward_list:    
        ward_arrays = [data[x] for x in ward_list]
        ward_bool = reduce((lambda x, y: x | y), ward_arrays)
        data = data[ward_bool]
    
    lats = data.Latitude
    lngs = data.Longitude
    text1 = data.owner_name
    text2 = data['Listed Real Value'].map(currency)
    text3 = data.Address
    text = text3 + "<br>" + "<b>Listed Owner:</b> " + text1 + "<br>" + "<b>Value:</b> " + text2
    
    return lats, lngs, text

def name_lister(name_string):
    """Creates a formatted list of names for use in other functions.

    Args:
        name_string (str): String of comma-separated names.
    
    Returns:
        name_list (list): List of names.
    
    """
    name_list = []

    if "," not in name_string:
        name_list.append(name_string)
    else:
        name_split = name_string.split(",")
        name_list = [x.strip() for x in name_split]
    
    return name_list

def get_ward_counts(name, ward_list):
    """Gets ward counts properties associated with name.

    Args:
        name (str): Last name associated with properties.
        ward_list (array): List of city wards for filtering.
    
    Returns:
        ward_counts (array): List of integers.
    """
    
    # Load data.
    df = name_search(name)
    data = pd.merge(df, geocodes, how='left', left_on='property_id', right_on='Parcel ID')

    # Filter wards.
    ward_arrays = [data[x] for x in ward_list]
    ward_bool = reduce((lambda x, y: x | y), ward_arrays)
    data = data[ward_bool]

    ward_counts = [sum(data[ward]) for ward in ward_list]

    return ward_counts

if __name__ == '__main__':
    app.run_server(debug=True)

