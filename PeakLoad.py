# =============================================================================
# Author            : Hale Kavoosi
# Email             : hlh.kavoosi@gmail.com
# Created Date      : 2021-12-17 00:00:00
# Last Modified Date:
# Last Modified By  :
# Version           : 1.1.0
# Python Version    : 3.5.2
# =============================================================================

import json
import sys
import time
from threading import Thread
from urllib.parse import unquote

import jdatetime
import pandas as pd
import psycopg2
import schedule
from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from mysql import connector

from BasicColumn_Convertor import BasicColumnConvertor

sys.path.insert(1, '/home/mpedc/program/configs/')
import dbconfigs
import servicesconfig

SERVICE_ID = 66
app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = servicesconfig.secret_key
cust_units_names = pd.DataFrame()

color = ["#B92B22", "#F78E40", "#F3E644", "#A7E336", "#708090", "#fc0ff5"]

data_ostan_active = {}  # پیک بار اکتیو استان(اکتیو)
data_ostan_reactive = {}  # پیک بار راکتیو استان(راکتیو)
data_ostan_active_tariff = {}  # پیک بار اکتیو استان بر اساس تعرفه
data_ostan_reactive_tariff = {}  # پیک بار راکتیو استان بر اساس تعرفه

data_shahrestan = {}  # پیک بار به ازای هر شهرستان(اکتیو)
data_shahrestan_reactive = {}  # پیک بار به ازای هر شهرستان(راکتیو)
data_factor = {}  # مجموع  RealEnergy به ازای هر شهرستان
category = {}  # month/day for a year
minDate = ""  # min year in "MeterInfo" table
maxDate = ""  # max year in "MeterInfo" table


def logger(*args):
    """
    logging function
    :return:
    """
    with open(__file__.split(".")[0] + ".log", "a") as f:
        print(jdatetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "->", *args, file=f)
    print(jdatetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "->", *args)


def get_postgresql_connection():
    """
    Connect to Postgresql
    :return: connection object
    """
    try:
        conn = psycopg2.connect(**dbconfigs.postgres_config)
        return conn
    except Exception as ex:
        logger("Error @get_postgresql_connection:", ex)
        return None


def get_memsql_connection():
    """
     Connect to memsql
     :return: connection object
      """
    try:
        conn = connector.connect(**dbconfigs.memsql_config)
        return conn
    except Exception as ex:
        logger("Error @get_memsql_connection:", ex)
        return None


def error_message(message, chart_filters=None):
    ret_json = [
        {
            "type": "msg",
            "data": [{'title': 'خطا', 'message': message, 'color': 'red'}]
        }
    ]
    if chart_filters is not None:
        ret_json += chart_filters
    return ret_json


def get_default_date(period):
    current = jdatetime.datetime.now() - jdatetime.timedelta(days=1)
    from_date = (current - jdatetime.timedelta(days=period)).strftime("%Y/%m/%d")
    to_date = current.strftime("%Y/%m/%d")
    return from_date, to_date


def get_cities_codes():
    conn = get_postgresql_connection()

    try:
        city_df = pd.read_sql(""" SELECT "unitName", cast("unitId" as varchar) as "UnitID" FROM "Units" """,
                              con=conn, params=())
        return city_df

    except Exception as error:
        logger("Error @get_cities_codes:", error)
        return None
    finally:
        if conn is not None:
            conn.close()


def create_line_chart(line_chart_list, _title, enabled):
    line_chart = json.load(open("BasicLine_base.json", "r"))
    line_chart["series"] = line_chart_list
    line_chart["title"]["text"] = _title
    line_chart["legend"]["enabled"] = enabled
    line_chart["yAxis"]["title"]["text"] = 'وات'
    return line_chart


def get_peakload_data_ostan():
    global data_ostan_active
    global data_ostan_reactive
    global data_ostan_active_tariff
    global data_ostan_reactive_tariff
    global minDate
    global maxDate
    global category

    conn = get_memsql_connection()

    try:
        # توان اکتیو
        data_ostan_active_tmp = pd.read_sql("""select convert(Date, char) as Date, meter_no, max(sum_power) as max
                                        from (select TimeTag as Date,
                                                     sum(PowerActiveAVG * CounterMultiple) as sum_power,
                                                     count(distinct M.MeterId) as meter_no 
                                              from DL.MeterInfo MI
                                                       inner join DL.Meter M on MI.ID = M.MeterId                                                  
                                                  and CounterMultiple is not null
                                                  and PowerActiveAVG is not null
                                                  and RIGHT(TimeTag, 4) = 0000
                                              group by TimeTag)
                                        group by LEFT(Date, 8)
                                        order by Date
                                        """, con=conn, params=())
        # توان راکتیو
        data_ostan_reactive_tmp = pd.read_sql("""select convert(Date, char) as Date, meter_no, max(sum_power) as max
                                                from (select TimeTag as Date,
                                                             sum(PowerReactiveAVG * CounterMultiple) as sum_power,
                                                             count(distinct M.MeterId) as meter_no
                                                      from DL.MeterInfo MI
                                                               inner join DL.Meter M on MI.ID = M.MeterId                                                  
                                                          and CounterMultiple is not null
                                                          and PowerActiveAVG is not null
                                                          and RIGHT(TimeTag, 4) = 0000
                                                      group by TimeTag)
                                                group by LEFT(Date, 8)
                                                order by Date
                                                """, con=conn, params=())
        # توان اکتیو بر اساس تعرفه
        data_ostan_active_tariff_tmp = pd.read_sql("""select convert(Date, char) as Date, UsageGroupCode,meter_no, max(sum_power) as max
                                                        from (select TimeTag as Date, UsageGroupCode,
                                                                     sum(PowerActiveAVG * CounterMultiple) as sum_power,
                                                                     count(distinct M.MeterId) as meter_no
                                                              from DL.MeterInfo MI
                                                                       inner join DL.Meter M on MI.ID = M.MeterId
                                                                  and CounterMultiple is not null
                                                                  and PowerActiveAVG is not null
                                                                  and RIGHT(TimeTag, 4) = 0000
                                                                  and UsageGroupCode is not null
                                                              group by TimeTag,UsageGroupCode)                                                    
                                                        group by LEFT(Date, 8), UsageGroupCode
                                                        order by Date
                                                     """, con=conn, params=())
        # توان راکتیو بر اساس تعرفه
        data_ostan_reactive_tariff_tmp = pd.read_sql("""select convert(Date, char) as Date, UsageGroupCode,meter_no, max(sum_power) as max
                                                        from (select TimeTag as Date, UsageGroupCode,
                                                                     sum(PowerReactiveAVG * CounterMultiple) as sum_power,
                                                                     count(distinct M.MeterId) as meter_no
                                                              from DL.MeterInfo MI
                                                                       inner join DL.Meter M on MI.ID = M.MeterId
                                                                  and CounterMultiple is not null
                                                                  and PowerActiveAVG is not null
                                                                  and RIGHT(TimeTag, 4) = 0000
                                                                  and UsageGroupCode is not null
                                                              group by TimeTag,UsageGroupCode)                                                    
                                                        group by LEFT(Date, 8), UsageGroupCode
                                                        order by Date
                                                     """, con=conn, params=())

        data_ostan_active_tmp.rename(columns={"max": "y"}, inplace=True)
        data_ostan_reactive_tmp.rename(columns={"max": "y"}, inplace=True)
        data_ostan_active_tariff_tmp.rename(columns={"max": "y"}, inplace=True)
        data_ostan_reactive_tariff_tmp.rename(columns={"max": "y"}, inplace=True)

        data_ostan_active_tmp['y'] = data_ostan_active_tmp['y'].round(decimals=2)
        data_ostan_reactive_tmp['y'] = data_ostan_reactive_tmp['y'].round(decimals=2)
        data_ostan_active_tariff_tmp['y'] = data_ostan_active_tariff_tmp['y'].round(decimals=2)
        data_ostan_reactive_tariff_tmp['y'] = data_ostan_reactive_tariff_tmp['y'].round(decimals=2)

        data_ostan_active_tmp["Year"] = data_ostan_active_tmp["Date"].str.slice(stop=4)
        data_ostan_reactive_tmp["Year"] = data_ostan_reactive_tmp["Date"].str.slice(stop=4)
        data_ostan_active_tariff_tmp["Year"] = data_ostan_active_tariff_tmp["Date"].str.slice(stop=4)
        data_ostan_reactive_tariff_tmp["Year"] = data_ostan_reactive_tariff_tmp["Date"].str.slice(stop=4)

        data_ostan_active_tmp["Month"] = data_ostan_active_tmp["Date"].str[4:6] + '/' + data_ostan_active_tmp[
                                                                                            "Date"].str[6:8]
        data_ostan_reactive_tmp["Month"] = data_ostan_reactive_tmp["Date"].str[4:6] + '/' + data_ostan_reactive_tmp[
                                                                                                "Date"].str[6:8]
        data_ostan_active_tariff_tmp["Month"] = data_ostan_active_tariff_tmp["Date"].str[4:6] + '/' + \
                                                data_ostan_active_tariff_tmp[
                                                    "Date"].str[6:8]
        data_ostan_reactive_tariff_tmp["Month"] = data_ostan_reactive_tariff_tmp["Date"].str[4:6] + '/' + \
                                                  data_ostan_reactive_tariff_tmp[
                                                      "Date"].str[6:8]

        data_ostan_active = data_ostan_active_tmp.copy()
        data_ostan_reactive = data_ostan_reactive_tmp.copy()
        data_ostan_active_tariff = data_ostan_active_tariff_tmp.copy()
        data_ostan_reactive_tariff = data_ostan_reactive_tariff_tmp.copy()

        minDate = data_ostan_active["Year"].min()
        maxDate = data_ostan_active["Year"].max()

        category["Month"] = data_ostan_active[data_ostan_active["Year"] == '1399']["Month"]

        return data_ostan_active, data_ostan_reactive, data_ostan_active_tariff, data_ostan_reactive_tariff, minDate, maxDate, category

    except Exception as error:
        logger("Error @get_peakload_data_ostan:", error)
        return None
    finally:
        if conn is not None:
            conn.close()


def get_peakload_data_shahrestan():
    global data_shahrestan
    global data_shahrestan_reactive

    conn = get_memsql_connection()

    try:
        data_shahrestan_tmp = pd.read_sql("""select convert(Date, char) as Date, meter_no, UnitID, max(sum_power) as max
                                                from (SELECT TimeTag                               as Date,
                                                             UnitID,
                                                             sum(PowerActiveAVG * CounterMultiple) as sum_power,
                                                             count(distinct M.MeterId) as meter_no
                                                      FROM DL.MeterInfo MI
                                                               inner join DL.Meter M on MI.ID = M.MeterId                                                                                                                  
                                                          and CounterMultiple is not null
                                                          and PowerActiveAVG is not null
                                                          and UnitID is not null
                                                          and RIGHT(TimeTag, 4) = 0000
                                                      GROUP BY TimeTag, UnitID
                                                      ORDER BY TimeTag)
                                                group by LEFT(Date, 8), UnitID
                                                ORDER BY Date
                                            """, con=conn, params=())

        data_shahrestan_reactive_tmp = pd.read_sql("""select convert(Date, char) as Date, meter_no, UnitID, max(sum_power) as max
                                                        from (SELECT TimeTag                               as Date,
                                                                     UnitID,
                                                                     sum(PowerReactiveAVG * CounterMultiple) as sum_power,
                                                                     count(distinct M.MeterId) as meter_no
                                                              FROM DL.MeterInfo MI
                                                                       inner join DL.Meter M on MI.ID = M.MeterId                                                                                                                  
                                                                  and CounterMultiple is not null
                                                                  and PowerActiveAVG is not null
                                                                  and UnitID is not null
                                                                  and RIGHT(TimeTag, 4) = 0000
                                                              GROUP BY TimeTag, UnitID
                                                              ORDER BY TimeTag)
                                                        group by LEFT(Date, 8), UnitID
                                                        ORDER BY Date
                                                    """, con=conn, params=())

        data_shahrestan_tmp.rename(columns={"max": "y"}, inplace=True)
        data_shahrestan_reactive_tmp.rename(columns={"max": "y"}, inplace=True)

        data_shahrestan_tmp["y"] = data_shahrestan_tmp["y"].round(decimals=2)
        data_shahrestan_reactive_tmp["y"] = data_shahrestan_reactive_tmp["y"].round(decimals=2)
        data_shahrestan_tmp["Year"] = data_shahrestan_tmp["Date"].str.slice(stop=4)
        data_shahrestan_reactive_tmp["Year"] = data_shahrestan_reactive_tmp["Date"].str.slice(stop=4)
        data_shahrestan_tmp["Month"] = data_shahrestan_tmp["Date"].str[4:6] + '/' + data_shahrestan_tmp["Date"].str[6:8]
        data_shahrestan_reactive_tmp["Month"] = data_shahrestan_reactive_tmp["Date"].str[4:6] + '/' + \
                                                data_shahrestan_reactive_tmp["Date"].str[6:8]
        data_shahrestan_tmp.loc[data_shahrestan_tmp["UnitID"] == '75', "UnitID"] = '70'
        data_shahrestan_reactive_tmp.loc[data_shahrestan_reactive_tmp["UnitID"] == '75', "UnitID"] = '70'

        data_shahrestan = data_shahrestan_tmp.copy()
        data_shahrestan_reactive = data_shahrestan_reactive_tmp.copy()

        return data_shahrestan, data_shahrestan_reactive

    except Exception as error:
        logger("Error @get_peakload_data_shahrestan:", error)
        return None
    finally:
        if conn is not None:
            conn.close()


def date_validation(date, name):
    error = ''
    if date in ["", "None"]:
        error = name + " را انتخاب نمایید."
    try:
        jdatetime.datetime.strptime(date, "%Y/%m/%d")
    except:
        error = name + " به درستی وارد نشده است."
    return error


def period_validation(sDate, eDate):
    error = ''
    if sDate >= eDate:
        error = " تاریخ شروع بازه باید از تاریخ پایان کوچکتر باشد."
    return error


# اگر از مقدار معادل سال قبل کمتر یا مساوی بود سبز
# اگه تا ۲۰% بیشتر بود زرد
# یشتر از ۲۰% تا ۵۰ % نارنجی
# بالای ۵۰ % قرمز
# اگر داده ی سال قبل موجود نبود آبی
def set_color_df(current_df, previous_year_df):
    df = pd.merge(current_df, previous_year_df, on="Month", how="outer", indicator=True, suffixes=('', '_pre')).query(
        '_merge in("left_only","both")')
    df["y_pre"] = df["y_pre"].where(pd.notnull(df["y_pre"]), 0)

    df.loc[df["y"] <= df["y_pre"], "color"] = "#28A745"  # green
    df.loc[(df["y"] > df["y_pre"]) & (df["y"] <= (df["y_pre"] + df["y_pre"] * 0.2)), "color"] = "#ffea07"  # yellow
    df.loc[(df["y"] > (df["y_pre"] + df["y_pre"] * 0.2)) & (
            df["y"] <= (df["y_pre"] + df["y_pre"] * 0.5)), "color"] = "#ff9100"  # orange
    df.loc[df["y"] > (df["y_pre"] + df["y_pre"] * 0.5), "color"] = "#FF0000"  # red
    df.loc[df["y_pre"] == 0, "color"] = "blue"  # blue

    return df[["Date", "meter_no", "y", "Year", "Month", "color"]]


# اگر از مقدار معادل سال قبل کمتر یا مساوی بود سبز
# اگه تا ۲۰% بیشتر بود زرد
# یشتر از ۲۰% تا ۵۰ % نارنجی
# بالای ۵۰ % قرمز
# اگر داده ی سال قبل موجود نبود آبی
def set_color_df_unit(current_df, previous_year_df):
    df = pd.merge(current_df, previous_year_df, on="UnitID", how="outer", indicator=True, suffixes=('', '_pre')).query(
        '_merge in("left_only","both")')
    df["y_pre"] = df["y_pre"].where(pd.notnull(df["y_pre"]), 0)

    df.loc[df["y"] <= df["y_pre"], "color"] = "#28A745"  # green
    df.loc[(df["y"] > df["y_pre"]) & (df["y"] <= (df["y_pre"] + df["y_pre"] * 0.2)), "color"] = "#ffea07"  # yellow
    df.loc[(df["y"] > (df["y_pre"] + df["y_pre"] * 0.2)) & (
            df["y"] <= (df["y_pre"] + df["y_pre"] * 0.5)), "color"] = "#ff9100"  # orange
    df.loc[df["y"] > (df["y_pre"] + df["y_pre"] * 0.5), "color"] = "#FF0000"  # red
    df.loc[df["y_pre"] == 0, "color"] = "blue"  # blue

    return df[["UnitID", "Date", "meter_no", "y", "Year", "Month", "color"]]


def make_chart_json(df, from_date, to_date, title):
    current_df = df[(df["Date"] > from_date.replace("/", "")) & (df["Date"] < to_date.replace("/", ""))]
    previous_year_df = df[(df["Date"] > str(int(from_date[:4]) - 1) + from_date[4:].replace("/", "")) & (
            df["Date"] < str(int(to_date[:4]) - 1) + to_date[4:].replace("/", ""))]

    df = set_color_df(current_df, previous_year_df)

    # add tooltip
    tooltip = "<br>{}: {:.2f}<br> " + 'تعداد کنتورهای قرائت شده:' + " {}"
    set_tooltip = lambda row: tooltip.format("توان اکتیو", row["y"], row["meter_no"])
    df["tooltip"] = df.apply(set_tooltip, axis=1)

    df = df[["Month", "y", "color", "tooltip"]]
    df.rename(columns={
        "Month": "name"
    }, inplace=True)

    df.sort_values(by="name", inplace=True)
    data_series = list()
    data_series.append({"name": title,
                        "data": df[["name", "y", "color", "tooltip"]].to_dict(orient="records")
                        })
    # set title
    title = title + " از تاریخ {} تا تاریخ {}".format(from_date, to_date)

    obj = BasicColumnConvertor(data_series, legend=False, title=title, yaxis_title='وات')
    chart_json = obj.convert_to_chart()

    return chart_json


def sched():
    schedule.every().day.at("07:00").do(get_peakload_data_ostan)
    schedule.every().day.at("07:00").do(get_peakload_data_shahrestan)
    while True:
        schedule.run_pending()
        time.sleep(1)


def sched2():
    get_peakload_data_ostan()
    get_peakload_data_shahrestan()


# -------------------------------------------------------------------------------------------------
# پیک بار در قسمت "شرکت" سامانه 360
# لاین چارت
@app.route('/company/loadpeak', methods=['GET'])
@cross_origin()
def peakLoad():
    input_params = request.args.to_dict()
    from_date_default, to_date_default = get_default_date(period=30)

    chart_filters = [{"type": "filter",
                      "data": [
                          {
                              "type": "groupSelector",
                              "param": "chart_type",
                              "data": {
                                  "line": "خطی",
                                  "chart": "ستونی"
                              },
                              "default_value": input_params.get("chart_type", "chart"),
                              "label": "نوع نمودار"
                          },
                          {
                              "type": "combo2",
                              "param": "tariff",
                              "data": [
                                  {"key": "0", "value": "کل"},
                                  {"key": "1", "value": "خانگی"},
                                  {"key": "2", "value": "عمومی"},
                                  {"key": "3", "value": "کشاورزی"},
                                  {"key": "4", "value": "صنعتی"},
                                  {"key": "5", "value": "سایر مصارف"}
                              ],
                              "default_value": input_params.get("tariff", "0"),
                              "label": "تعرفه"
                          },
                          {
                              "type": "groupSelector",
                              "param": "period",
                              "data": {
                                  "yearly": "سالانه",
                                  "daily": "پیوسته"
                              },
                              "default_value": input_params.get("period", "yearly"),
                              "label": "بازه‌ی نمایش",
                              "groupId": "line"
                          },
                          {
                              "type": "date",
                              "param": "from_date",
                              "default_value": input_params.get("from_date", from_date_default),
                              "label": "تاریخ شروع",
                              "groupId": ["chart", "daily"]
                          },
                          {
                              "type": "date",
                              "param": "to_date",
                              "default_value": input_params.get("to_date", to_date_default),
                              "label": "تاریخ پایان",
                              "groupId": ["chart", "daily"]
                          }
                      ],
                      "onclick": [
                          {
                              "params": input_params,
                              "indicatorid": "332",
                              "type": "company",
                              "method": "get"
                          }
                      ]
                      }]

    try:
        chart_type = input_params.get('chart_type', "chart")
        period = input_params.get('period', "yearly")
        tariff = input_params.get('tariff', "0")
        from_date = input_params.get('from_date', from_date_default)
        to_date = input_params.get('to_date', to_date_default)

        # در صورت انتخاب تعرفه
        if tariff != "0":
            df = data_ostan_active_tariff.loc[data_ostan_active_tariff["UsageGroupCode"] == tariff]
            df_reactive = data_ostan_reactive_tariff.loc[data_ostan_reactive_tariff["UsageGroupCode"] == tariff]
        else:
            df = data_ostan_active
            df_reactive = data_ostan_reactive

        min = minDate
        max = maxDate

        if df.empty:
            ret_json = error_message(' داده ای جهت نمایش وجود ندارد.', chart_filters)
            return jsonify(ret_json), 400

        if chart_type == 'chart' or (chart_type == 'line' and period == 'daily'):
            error = date_validation(from_date, 'تاریخ شروع')
            if error != '':
                ret_json = error_message(error, chart_filters)
                return jsonify(ret_json), 400

            error = date_validation(to_date, 'تاریخ پایان')
            if error != '':
                ret_json = error_message(error, chart_filters)
                return jsonify(ret_json), 400

            error = period_validation(from_date, to_date)
            if error != '':
                ret_json = error_message(error, chart_filters)
                return jsonify(ret_json), 400

        if chart_type == "line":
            data_series = list()
            data_series_reactive = list()

            # add tooltip
            tooltip = "<br>{}:<br>{}: {:.2f}<br> " + 'تعداد کنتورهای قرائت شده:' + " {}"
            set_tooltip = lambda row: tooltip.format(row["Year"], "توان اکتیو", row["y"], row["meter_no"])
            df["tooltip"] = df.apply(set_tooltip, axis=1)

            # add tooltip
            set_tooltip = lambda row: tooltip.format(row["Year"], "توان راکتیو", row["y"], row["meter_no"])
            df_reactive["tooltip"] = df_reactive.apply(set_tooltip, axis=1)

            if period == 'daily':
                legend_enable = False

                # timestamp for x axis
                df["TimeTag"] = df["Date"].apply(
                    lambda x: jdatetime.datetime.strptime(x, "%Y%m%d%H%M%S").timestamp())
                df_reactive["TimeTag"] = df_reactive["Date"].apply(
                    lambda x: jdatetime.datetime.strptime(x, "%Y%m%d%H%M%S").timestamp())

                df["x"] = df["TimeTag"] * 1000
                df_reactive["x"] = df_reactive["TimeTag"] * 1000

                dataList = df[(df["Date"] > from_date.replace("/", "")) & (df["Date"] < to_date.replace("/", ""))][
                    ["x", "y", "tooltip"]].values.tolist()
                dataList_reactive = df_reactive[(df_reactive["Date"] > from_date.replace("/", "")) & (
                        df_reactive["Date"] < to_date.replace("/", ""))][["x", "y", "tooltip"]].values.tolist()

                data_series.append({"name": 'توان اکتیو',
                                    "keys": ["x", "y", "tooltip"],
                                    "data": dataList,
                                    "color": "#B92B22"
                                    })
                data_series_reactive.append({"name": 'توان راکتیو',
                                             "keys": ["x", "y", "tooltip"],
                                             "data": dataList_reactive,
                                             "color": "#B92B22"
                                             })

            else:
                # timestamp for x axis
                df["TimeTag"] = df["Date"].apply(
                    lambda x: jdatetime.datetime.strptime(x, "%Y%m%d%H%M%S").replace(year=1399, hour=0, minute=0,
                                                                                     second=0).timestamp())
                df_reactive["TimeTag"] = df_reactive["Date"].apply(
                    lambda x: jdatetime.datetime.strptime(x, "%Y%m%d%H%M%S").replace(year=1399, hour=0, minute=0,
                                                                                     second=0).timestamp())

                df["x"] = df["TimeTag"] * 1000
                df_reactive["x"] = df_reactive["TimeTag"] * 1000

                legend_enable = True
                visible = False
                for i in range(int(min), int(max) + 1):
                    if i == int(max):
                        visible = True
                    dataList = df[df["Year"] == str(i)][["x", "y", "tooltip"]].values.tolist()
                    dataList_reactive = df_reactive[df_reactive["Year"] == str(i)][
                        ["x", "y", "tooltip"]].values.tolist()

                    data_series.append({"name": i,
                                        "keys": ["x", "y", "tooltip"],
                                        "data": dataList,
                                        "color": color[i - int(min)],
                                        'visible': visible})
                    data_series_reactive.append({"name": i,
                                                 "keys": ["x", "y", "tooltip"],
                                                 "data": dataList_reactive,
                                                 "color": color[i - int(min)],
                                                 'visible': visible})

            chart_json_active = create_line_chart(data_series, "توان اکتیو", legend_enable)
            chart_json_reactive = create_line_chart(data_series_reactive, "توان راکتیو", legend_enable)

            if len(chart_json_active) == 0 or len(chart_json_reactive) == 0:
                ret_json = error_message(' داده ای جهت نمایش وجود ندارد.', chart_filters)
                return jsonify(ret_json), 400

        # chart
        elif chart_type == "chart":
            # --------active
            chart_json_active = make_chart_json(df, from_date, to_date, "توان اکتیو")

            # --------reactive
            chart_json_reactive = make_chart_json(df_reactive, from_date, to_date, "توان راکتیو")

        ret_json = chart_filters.copy()
        ret_json += [{"type": "chart", "data": chart_json_active},
                     {"type": "chart", "data": chart_json_reactive}]
        return jsonify(ret_json), 200

    except Exception as err:
        logger("Error @peakLoad:", err)
        return jsonify({"msg": [{'title': 'خطا', 'message': 'خطایی رخ داده است!', 'color': 'red'}]}), 400


# پیک بار شهرستان در قسمت "شهرستان" سامانه 360
# لاین چارت
@app.route('/unit/loadpeak', methods=['GET'])
@cross_origin()
def peakLoad_shahrestan():
    unitId = request.args['unitid']

    try:
        # get data
        df = data_shahrestan
        df_reactive = data_shahrestan_reactive

        min = minDate
        max = maxDate

        if df.empty:
            ret_json = error_message(' داده ای جهت نمایش وجود ندارد.')
            return jsonify(ret_json), 400

        df = df[df["UnitID"] == unitId]
        df_reactive = df_reactive[df_reactive["UnitID"] == unitId]

        # add tooltip
        tooltip = "<br>{}:<br>{}: {:.2f}<br> " + 'تعداد کنتورهای قرائت شده:' + " {}"
        set_tooltip = lambda row: tooltip.format(row["Year"], "توان اکتیو", row["y"], row["meter_no"])
        df["tooltip"] = df.apply(set_tooltip, axis=1)
        set_tooltip = lambda row: tooltip.format(row["Year"], "توان راکتیو", row["y"], row["meter_no"])
        df_reactive["tooltip"] = df_reactive.apply(set_tooltip, axis=1)

        # timestamp for x axis
        df["TimeTag"] = df["Date"].apply(
            lambda x: jdatetime.datetime.strptime(x, "%Y%m%d%H%M%S").replace(year=1399, hour=0, minute=0,
                                                                             second=0).timestamp())
        df_reactive["TimeTag"] = df_reactive["Date"].apply(
            lambda x: jdatetime.datetime.strptime(x, "%Y%m%d%H%M%S").replace(year=1399, hour=0, minute=0,
                                                                             second=0).timestamp())
        df["x"] = df["TimeTag"] * 1000
        df_reactive["x"] = df_reactive["TimeTag"] * 1000

        # line chart for each year
        data_series = list()
        data_series_reactive = list()
        visible = False
        for i in range(int(min), int(max) + 1):
            if i == int(max) - 1:
                visible = True
            dataList = df[df["Year"] == str(i)][["x", "y", "tooltip"]].values.tolist()
            dataList_reactive = df_reactive[df_reactive["Year"] == str(i)][["x", "y", "tooltip"]].values.tolist()

            data_series.append({"name": i,
                                "keys": ["x", "y", "tooltip"],
                                "data": dataList,
                                "color": color[i - int(min)],
                                'visible': visible})
            data_series_reactive.append({"name": i,
                                         "keys": ["x", "y", "tooltip"],
                                         "data": dataList_reactive,
                                         "color": color[i - int(min)],
                                         'visible': visible})

        chart_json = create_line_chart(data_series, "توان اکتیو", True)
        chart_json_reactive = create_line_chart(data_series_reactive, "توان راکتیو", True)

        if len(chart_json) == 0 or len(chart_json_reactive) == 0:
            ret_json = error_message(' داده ای جهت نمایش وجود ندارد.')
            return jsonify(ret_json), 400

        ret_json = [{"type": "chart", "data": chart_json},
                    {"type": "chart", "data": chart_json_reactive}]
        return jsonify(ret_json), 200

    except Exception as err:
        logger("Error @peakLoad_shahrestan:", err)
        return jsonify({"msg": [{'title': 'خطا', 'message': 'خطایی رخ داده است!', 'color': 'red'}]}), 400


# پیک بار به تفکیک شهرستان در قسمت "شرکت" سامانه 360
# نقشه و ستونی
@app.route('/company/sepratedloadpeak', methods=['GET'])
@cross_origin()
def peakLoad_seprated():
    input_params = request.args.to_dict()
    from_date_default, to_date_default = get_default_date(period=30)
    chart_filters = [{
        "type": "filter",
        "data": [
            {
                "type": "date",
                "param": "from_date",
                "default_value": input_params.get("from_date", from_date_default),
                "label": "تاریخ شروع"
            },
            {
                "type": "date",
                "param": "to_date",
                "default_value": input_params.get("to_date", to_date_default),
                "label": "تاریخ پایان"
            },
            {
                "type": "combo2",
                "param": "chart_type",
                "data": [
                    {"key": "map", "value": "نقشه"},
                    {"key": "chart", "value": "ستونی"}
                ],
                "default_value": input_params.get("chart_type", "chart"),
                "label": "نوع نمودار"
            }
        ],
        "onclick": [
            {
                "params": input_params,
                "indicatorid": "362",
                "type": "company",
                "method": "get"
            }
        ]
    }]

    try:
        # get input parameters
        from_date = unquote(input_params.get('from_date', from_date_default))
        to_date = unquote(input_params.get('to_date', to_date_default))
        chart_type = input_params.get('chart_type', "chart")

        # preprocess input data
        if int(from_date.replace("/", "")) > int(to_date.replace("/", "")):
            ret_json = error_message('تاریخ شروع باید قبل از تاریخ پایان باشد.', chart_filters)
            return jsonify(ret_json), 400
        if int(from_date.replace("/", "")) > int(jdatetime.datetime.now().strftime("%Y%m%d")):
            ret_json = error_message('تاریخ شروع باید قبل از تاریخ امروز باشد.', chart_filters)
            return jsonify(ret_json), 400

        # get data
        df = data_shahrestan

        if df.empty:
            ret_json = error_message(' داده ای جهت نمایش وجود ندارد.', chart_filters)
            return jsonify(ret_json), 400

        current_df = df[(df["Date"] > from_date.replace("/", "")) & (df["Date"] < to_date.replace("/", ""))]

        previous_year_df = df[(df["Date"] > str(int(from_date[:4]) - 1) + from_date[4:].replace("/", "")) & (
                df["Date"] < str(int(to_date[:4]) - 1) + to_date[4:].replace("/", ""))]

        current_df = current_df.groupby(["UnitID"], as_index=False).max()
        current_df = current_df.where(pd.notnull(df), 0)

        previous_year_df = previous_year_df.groupby(["UnitID"], as_index=False).max()
        previous_year_df = previous_year_df.where(pd.notnull(df), 0)

        # add color
        df = set_color_df_unit(current_df, previous_year_df)

        # add city_name, city_code
        df = pd.merge(df, get_cities_codes(), how='left', on='UnitID')

        # add tooltip
        tooltip = "<br>{}:<br>{}: {:.2f}<br> " + 'تعداد کنتورهای قرائت شده:' + " {}"
        set_tooltip = lambda row: tooltip.format(row["Year"], "توان اکتیو", row["y"], row["meter_no"])
        df["tooltip"] = df.apply(set_tooltip, axis=1)

        df.sort_values(by="y", ascending=True, inplace=True)

        df = df[["unitName", "UnitID", "y", "color", "tooltip"]]
        df.rename(columns={
            "unitName": "name",
            "UnitID": "id"
        }, inplace=True)

        # set title
        title = "پیک بار به تفکیک شهرستان از تاریخ {} تا تاریخ {}".format(from_date, to_date)

        # map
        if chart_type == "map":
            chart = json.load(open("map.json", "r"))
            chart["series"][0]["data"] = df[["y", "id", "color", "tooltip"]].to_dict(orient="records")
            chart["title"]["text"] = title

            ret_json = chart_filters.copy()
            ret_json += [{"type": "map", "data": chart}]
            return jsonify(ret_json), 200

        # bar chart
        elif chart_type == "chart":
            df.sort_values(by="y", ascending=False, inplace=True)
            data_series = list()
            data_series.append({"name": "پیک بار به تفکیک شهرستان",
                                "data": df[["name", "y", "color", "tooltip"]].to_dict(orient="records")
                                })

            obj = BasicColumnConvertor(data_series, legend=False, title=title, yaxis_title='وات')
            chart_json = obj.convert_to_chart()

            ret_json = chart_filters.copy()
            ret_json += [{"type": "chart", "data": chart_json}]
            return jsonify(ret_json), 200

    except Exception as err:
        logger("Error @peakLoad_seprated:", err)
        return jsonify({"msg": [{'title': 'خطا', 'message': 'خطایی رخ داده است!', 'color': 'red'}]}), 400


# this route is just for manually update by postman
@app.route('/company/prepare_data', methods=['GET'])
def prepare_data():
    try:
        th = Thread(target=sched2)
        th.setDaemon(True)
        th.start()
        return 'Ok', 200
    except Exception as err:
        logger("Error @prepare_data:", err)
        return 'Errors', 500


if __name__ == '__main__':
    sched2()
    thread = Thread(target=sched)
    thread.setDaemon(True)
    thread.start()
    app.run(host='0.0.0.0', port=5061, debug=False, use_reloader=False)
