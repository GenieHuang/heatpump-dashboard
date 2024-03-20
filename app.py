# imports
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry

import lets_plot as lp
import numpy as np
from shiny import App, Inputs, Outputs, Session, reactive, render, req, ui
from shinywidgets import render_widget, output_widget

from ipyleaflet import Map,Marker
from ipywidgets import Layout

# Requesting histrical weather API
def historical_weather(lat, lng, start_date, end_date, units):
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,               # input
        "longitude": lng,              # input
        "start_date": start_date,      # input
        "end_date": end_date,        # input
        "daily": "temperature_2m_min",   # fixed
        "temperature_unit": units # input
    }

    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation {response.Elevation()} m asl")
    print(f"Timezone {response.Timezone()} {response.TimezoneAbbreviation()}")
    print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")

    # Process daily data. The order of variables needs to be the same as requested.
    daily = response.Daily()
    daily_temperature_2m_min = daily.Variables(0).ValuesAsNumpy()

    daily_data = {"date": pd.date_range(
        start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
        end = pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
        freq = pd.Timedelta(seconds = daily.Interval()),
        inclusive = "left"
    )}
    daily_data["temperature_2m_min"] = daily_temperature_2m_min

    daily_dataframe = pd.DataFrame(data = daily_data)
    return daily_dataframe, response.Latitude(),response.Longitude()

# lets-plot setup
lp.LetsPlot.setup_html()

# create full and tidy data
cities = pd.read_csv("data/cities.csv")

# Convert city_state column to list
city_list = cities['city_state'].tolist()

# setup ui
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_selectize("city", "City", city_list, selected="Urbana,Illinois"),
        ui.output_text("selected_lat_lng"),
        ui.input_date_range("dates", "Dates", start="2022-01-01", end="2024-01-01",max="2024-01-01",min="2020-01-01"),
        ui.input_numeric("forecast_year", "Years to Forecast", 1, min=1, max=5),
        ui.input_radio_buttons( "forecast_trend",  "Forecast Trend",  {"1": "Flat", "2": "Linear"}, selected="1"),  
        ui.input_radio_buttons( "units",  "Units",  {"fahrenheit": "Fahrenheit", "celsius": "Celsius"}, selected="fahrenheit"),  
        ui.output_ui("plot_temp_slider"),
        ui.input_checkbox_group("plot_options","Plot Options",choices=["Weekly Rolling Average","Monthly Rolling Average"],inline=False),
        ui.output_ui("table_temp_slider"),
        ui.hr(),
        output_widget("map"),
        width=350,
        open='always'
    ),
    ui.page_navbar(
        ui.nav_panel("Historical",
                     ui.output_ui("historical_plot"),
                     ui.hr(),
                     ui.output_data_frame("historical_df")),
        ui.nav_panel("Forecast",
                     ui.output_ui("forecast_plot"),
                     ui.hr(),
                     ui.output_data_frame("forecast_df")),
        ui.nav_panel("About"),
    ),
    title = "Daily Heat Pump Efficiency Counter",
)


# setup server
def server(input: Inputs, output: Outputs, session: Session):
    def get_data():

        # Params
        lat, lng = current_lat_lng()
        start_date = input.dates()[0]
        end_date = input.dates()[1]
        units = input.units()

        # Getting historical weather data
        daily_dataframe, lat, lng = historical_weather(lat, lng,start_date, end_date, units)

        return daily_dataframe, lat, lng

    def current_lat_lng():
        selected_city = input.city()
        # Get the lat and lng of the selected city_state
        selected_lat_lng= cities[cities["city_state"] == selected_city].iloc[0]
        lat = selected_lat_lng["lat"]
        lng = selected_lat_lng["lng"]
        return lat,lng
    
    @output
    @render.text("selected_lat_lng")
    def selected_lat_lng():
        _, lat, lng = get_data()
        return f"{lat:.4f}°N, {lng:.4f}°E"
    
    @render_widget("map")
    def map():
        _, lat, lng = get_data()
        map = Map(center = (lat,lng), zoom = 12, layout=Layout(height='200px'))
        marker = Marker(location=(lat, lng))
        map.add_layer(marker)
        return map
    
    @render.data_frame("historical_df") 
    def historical_df():
        return render.DataGrid(calculate_table(),summary=False,height='3000px',width=1600)
    
    @reactive.Calc
    def calculate_table():
        selected_temp = input.table_temp()
        temp_list = list(range(selected_temp[1], selected_temp[0] - 1, -1))
        historical_rows = []
        daily_dataframe,_,_ = get_data()
        temp_table = daily_dataframe[['temperature_2m_min']].astype(float)
        
        for temp in temp_list:
                days_below = temp_table[temp_table["temperature_2m_min"] < temp].shape[0]
                proportion_below = round(days_below / temp_table.shape[0],3)
                historical_rows.append({
                    "Temp": temp,
                    "Days Below": days_below,
                    "Proportion Below": proportion_below
                })

        historical_df = pd.DataFrame(historical_rows)
        return historical_df
    
    @output
    @render.ui("plot_temp_slider")
    def plot_temp_slider():
        units = input.units()
        if units == "fahrenheit":
            return ui.input_slider("plot_temp", "Plot Temperature", min=-15, max=50, step=1, value=5)
        else:  # Celsius
            return ui.input_slider("plot_temp", "Plot Temperature", min=-25, max=10, step=1, value=-15)
    
    @output
    @render.ui("table_temp_slider")
    def table_temp_slider():
        units = input.units()
        if units == "fahrenheit":
            return ui.input_slider("table_temp", "Table Temperature", min=-25, max=60, step=1, value=[0,15])
        else:  # Celsius
            return ui.input_slider("table_temp", "Table Temperature", min=-30, max=15, step=1, value=[-20,-10])

    @output
    @render.ui("historical_plot")
    def historical_plot():
        daily_dataframe,_,_ = get_data()
        daily_dataframe["date"] = pd.to_datetime(daily_dataframe["date"])

        daily_dataframe["weekly_rolling"] = daily_dataframe["temperature_2m_min"].rolling(window=7).mean()
        daily_dataframe["monthly_rolling"] = daily_dataframe["temperature_2m_min"].rolling(window=30).mean()

        selected_temp_line = input.plot_temp()

        date_range = pd.date_range("2020-01-01","2024-01-01", freq="3M")
        breaks_list = date_range.tolist()

        plot_options = input.plot_options()

        p = (
            lp.ggplot(daily_dataframe, lp.aes(x="date"))
            + lp.geom_point(lp.aes(y="temperature_2m_min"), color="grey", alpha=0.5) 
            + lp.geom_point(lp.aes(y="temperature_2m_min"), 
                    color="black",
                    data=daily_dataframe[daily_dataframe['temperature_2m_min'] > selected_temp_line])

            + lp.geom_hline(yintercept=selected_temp_line, color="black", size=0.5, show_legend=False)
            + lp.ggsize(width = 1400, height = 500)
            + lp.labs(x="",y="Daily Minimum Temperature °F")
            + lp.scale_x_datetime(breaks=breaks_list,format="%Y-%m")
            + lp.theme(panel_border=lp.element_rect(color="black",size=1),
                       axis_title=lp.element_text(face="bold"),
                       axis_text_x = lp.element_text(angle=0))
        )

        if "Weekly Rolling Average" in plot_options:
            p += lp.geom_line(lp.aes(y="weekly_rolling"), color = "orange", size = 1)

        if "Monthly Rolling Average" in plot_options:
            p += lp.geom_line(lp.aes(y="monthly_rolling"), color = "blue", size = 1)
            
        phtml = lp._kbridge._generate_static_html_page(p.as_dict(), iframe=True)

        # Return the HTML to be rendered in the Shiny app
        return ui.HTML(phtml)

# run app
app = App(app_ui, server)