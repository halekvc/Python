# =============================================================================
# Author            : Hale Kavoosi
# Email             : hlh.kavoosi@gmail.com
# Created Date      : 2021-06-26 00:00:00
# Last Modified Date:
# Last Modified By  :
# Version           : 1.1.0
# Python Version    : 3.5.2
# =============================================================================

import json
import multiprocessing
# We must import this explicitly, it is not imported by the top-level
# multiprocessing module.
import multiprocessing.pool
import re
import sys
from functools import reduce
from functools import wraps
import jdatetime
import jwt
import pandas as pd
import psycopg2
import requests
from flask import Flask, request, jsonify
import StackedColumn_Convertor as sc
import numpy

sys.path.insert(1, '/home/hduser/program/configs/')
import dbconfigs
import servicesconfig

SERVICE_ID = 116
postgres_config2 = dbconfigs.postgres_config

app = Flask(__name__)

app.config['SECRET_KEY'] = servicesconfig.secret_key

anacav_auth = servicesconfig.anacav_auth
LOGIN_UERNAME = anacav_auth["username"]
LOGIN_PASSWORD = anacav_auth["password"]


class NoDaemonProcess(multiprocessing.Process):
    # make 'daemon' attribute always return False
    def _get_daemon(self):
        return False

    def _set_daemon(self, value):
        pass

    daemon = property(_get_daemon, _set_daemon)


# We sub-class multiprocessing.pool.Pool instead of multiprocessing.Pool
# because the latter is only a wrapper function, not a proper class.
class MyPool(multiprocessing.pool.Pool):
    Process = NoDaemonProcess


def login():
    try:
        _url = "http://172.30.10.150:5000/login"
        _headers = {"Content-Type": "application/json"}
        _json = {"username": LOGIN_UERNAME, "password": LOGIN_PASSWORD}
        login_req = requests.post(_url, headers=_headers, json=_json)
        token = json.loads(login_req.text)['token']
        return token
    except Exception as error:
        print("Login Error")
        return ""


def logger(*args):
    """
    logging function
    :return:
    """
    with open(__file__.split(".")[0] + ".log", "a") as f:
        print(jdatetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "->", *args, file=f)
    print(jdatetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "->", *args)


def get_default_date(period):
    current = jdatetime.datetime.now() - jdatetime.timedelta(days=1)
    from_date = (current - jdatetime.timedelta(days=period)).strftime("%Y/%m/%d")
    to_date = current.strftime("%Y/%m/%d")
    return from_date, to_date


def get_default_enddate(period):
    current = jdatetime.datetime.now() - jdatetime.timedelta(days=1)
    from_date = (current - jdatetime.timedelta(days=period)).strftime("%Y/%m/%d")
    return from_date


def get_current_date():
    current = jdatetime.datetime.now().strftime("%Y/%m/%d")
    return current


def get_current_date_gregorian():
    current = jdatetime.datetime.now().togregorian().strftime("%Y-%m-%d %H:%M:%S.%f")[:-4]
    return current


def shamsi_to_gregorian(date):
    date = jdatetime.datetime.strptime(date, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")
    return date


def get_shamsi_date(date):
    _date = jdatetime.datetime.fromgregorian(date=date).strftime('%Y/%m/%d %H:%M:%S')
    return _date


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
        error = " تاریخ شروع بازه ها باید از تاریخ پایان آنها کوچکتر باشد."
    return error


def get_postgresql_connection():
    """
    Connect to Postgresql
    :return: connection object
    """
    try:
        conn = psycopg2.connect(**postgres_config2)
        return conn
    except Exception as ex:
        logger("Error @get_postgresql_connection:", ex)
        return None


def clear_input_params(inp_req_args):
    req_args = {}
    for k, v in inp_req_args.items():
        if v != 'undefined' and v != '':
            req_args[k] = v
    return req_args


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'x-access-token' in request.headers:
            token = request.headers['x-access-token']
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        connection = get_postgresql_connection()
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'])
            pid = data['public_id']
            res = pd.read_sql('select "public_id" from public."RestUsers" inner join public."RestUserService" '
                              'on public."RestUsers"."ID"=public."RestUserService"."userid" '
                              'where "public_id" = %s and "serviceid" = %s  and "is_active" = True ',
                              connection, params=(pid, SERVICE_ID))
            if res.empty:
                return jsonify({'message': 'Access denied.'}), 401
        except Exception as err:
            return jsonify({'message': 'Access denied.'}), 401
        finally:
            if connection is not None:
                connection.close()
        return f(res, *args, **kwargs)

    return decorated


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


def err_msg(msg, chart_filters=None):
    ret_json = [{"type": "msg", "data": [{'title': 'پیام', 'message': msg, 'color': 'red'}]}]
    if chart_filters is not None:
        ret_json += chart_filters
    return ret_json


def err_msg2(msg, chart_filters=None):
    ret_json = [{"type": "msg2", "data": [{'title': 'پیام', 'message': msg, 'icon': 'success'}]}]
    if chart_filters is not None:
        ret_json += chart_filters
    return ret_json


def err_msg_list(msg_list, chart_filters=None):
    data = []
    for msg in msg_list:
        msg = {'title': 'پیام', 'message': msg, 'color': 'red'}
        data.append(msg)
    ret_json = [{"type": "msg", "data": data}]
    print(ret_json)
    if chart_filters is not None:
        ret_json += chart_filters
    return ret_json


def check_permission(token):
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'])
        user_id = data.get("id")
        user_name = data.get("username")
        fullname = data.get("fullname")
        user_info = {'user_id': user_id, 'user_name': user_name, 'fullname': fullname}
        return user_info
    except:
        return None


def get_cities_codes(omoor):
    conn = get_postgresql_connection()
    try:
        query = """ SELECT "OmoorCode", "OmoorNmae" as "OmoorName" FROM "DW_Omoor" """
        if omoor == '0':
            df = pd.read_sql(query
                             , con=conn, params=())
        else:
            df = pd.read_sql(query + """ where "OmoorCode"=%s """
                             , con=conn, params=(omoor,))
        return df

    except Exception as error:
        logger("Error @get_cities_codes:", error)
        return None
    finally:
        if conn is not None:
            conn.close()


def OmoorCombo():
    connection = get_postgresql_connection()
    try:
        res = pd.read_sql(''' SELECT "OmoorCode", "OmoorNmae" FROM public."DW_Omoor" order by "OmoorNmae" ''',
                          connection, params=())
        Omoor = [{"key": "0", "value": "همه"}]
        for i in res.values.tolist():
            Omoor += {"key": i[0], "value": i[1]},
        return Omoor

    except Exception as error:
        logger("Error @search_location: ", error)
        return None
    finally:
        if connection is not None:
            connection.close()


def get_source():
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql("""SELECT id, "persianName" FROM "BPM"."Sources" where id not IN (0,2)
                                    and "IsActive"=true order by id """,
                             connection, params=())

        source_list = [{"key": "0", "value": "انتخاب کنید"}]
        for i in result.values.tolist():
            source_list.append({"key": i[0], "value": i[1]})

        return source_list

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# کمبوی فرآیند
def get_process(selected_source):
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql("""select "id" ,"name" from "BPM"."Process" where "processLetter" is NULL
                                and "sourceId"=%s order by "name" """, connection, params=(selected_source,))

        process_list = []
        for i in result.values.tolist():
            process_list += {"key": i[0], "value": i[1]},
        return process_list

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# کمبوی مراحل
def get_states_combo(processId):
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql(
            """select "id" ,"sourceStateName" from "BPM"."ProcessState" where "processId" = %s order by "sort" """,
            connection, params=(processId,))

        states_list = []
        for i in result.values.tolist():
            states_list += {"key": i[0], "value": i[1]},
        return states_list

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# کمبوی مراحل مشترک
def get_states_common_combo():
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql(
            """ SELECT "Id", "stateName" FROM "BPM"."CommonStates" order by "stateName" """,
            connection, params=())

        states_list = []
        for i in result.values.tolist():
            states_list += {"key": i[0], "value": i[1]},
        return states_list

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# به دست آوردن stateId مراحل انتخاب شده در مراحل مشترک
def get_states_common(selected_states_list):
    connection = get_postgresql_connection()
    try:
        if type(selected_states_list) is str:
            selected_states_list = tuple(selected_states_list.split(","))
        else:
            selected_states_list = tuple(selected_states_list)
        result = pd.read_sql(
            """ select distinct "stateId" from "BPM"."CommonStatesMap" where "commonStateId" in %s """,
            connection, params=(selected_states_list,))

        states_list = result["stateId"].values.tolist()
        return states_list

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# به دست آوردن نام مرحله برای نامگذاری تب ها در گزارش بر اساس فرآیند
def get_state_name(stateId):
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql("""select "id" ,"sourceStateName" from "BPM"."ProcessState" where "id"=%s """,
                             connection, params=(stateId,))

        # state_name = ''
        # for i in result["sourceStateName"].values.tolist():
        #     state_name += i + ", "
        # state_name = state_name[0:-2]
        state_name = result.iloc[0]["sourceStateName"]
        return "اطلاعات کارتابل " + state_name

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# به دست آوردن نام مرحله برای نامگذاری تب ها در گزارش بر اساس مرحله
def get_commonState_name(stateId):
    connection = get_postgresql_connection()
    try:
        if type(stateId) is str:
            result = pd.read_sql("""select "Id" ,"stateName" from "BPM"."CommonStates" where "Id"=%s """, connection,
                                 params=(stateId,))

            # state_name = ''
            # for i in result["sourceStateName"].values.tolist():
            #     state_name += i + ", "
            # state_name = state_name[0:-2]
            state_name = result.iloc[0]["stateName"]
            return "اطلاعات کارتابل " + state_name

        else:
            return "مجموع مراحل منتخب"

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# کمبوی فرآیند در گزارشات بر اساس مرحله ی انتخابی(مرحله‌ی انتخابی در کدام فرآیندها وجود دارد
def get_processes(selected_commonstates):
    connection = get_postgresql_connection()
    try:
        selected_commonstates = tuple(selected_commonstates.split(","))

        result = pd.read_sql("""select distinct "processId", name from "BPM"."CommonStatesMap"
                                inner join "BPM"."ProcessState" on "BPM"."ProcessState"."id"="BPM"."CommonStatesMap"."stateId" 
                                inner join "BPM"."Process" on "BPM"."Process"."id"="BPM"."ProcessState"."processId"
                                where "commonStateId" in %s order by name """
                             , connection, params=(selected_commonstates,))

        processes_list = []
        for i in result.values.tolist():
            processes_list += {"key": i[0], "value": i[1]},
        return processes_list

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# نمونه گردش هایی که در یک بازه‌ی خاص شروع شده اند ولی هنوز تا به امروز تمام نشده اند
# اگر یک گردش چند بار به یک مرحله برود ما تمام آن دفعات را حساب میکنیم
def get_instance_count(statesId, process, sDate, eDate, omoor, reportBase):
    connection = get_postgresql_connection()
    try:
        statesId = tuple(statesId.split(","))
        process = tuple(process.split(","))
        omoor = int(omoor)
        # p = time.time()

        query = """ select "OmoorCode", "States".id as "instanceId", "previousInstanceId"
                                            from "BPM".instance inner join 
                                            "BPM"."States" on "BPM".instance."id" = "BPM"."States"."instanceId"
                                            and "stateId" in %s and "stateEndDate" is NULL
                                            and date("stateStartDate") between %s and %s
                                            and "BPM".instance."statusType"=1
                                            and "processId" in %s
                                            inner join public."DW_Omoor"
                                            on "BPM".instance."unitId" = public."DW_Omoor"."OmoorCode"                                                                       
                                             """
        if omoor == 0:
            result = pd.read_sql(query, connection,
                                 params=(statesId, sDate, eDate, process,))
        else:
            result = pd.read_sql(query + """ and "OmoorCode"=%s 
                                         """, connection, params=(statesId, sDate, eDate, process, omoor,))

        # print("direct query: " + str(time.time() - p))
        # print(statesId, process, sDate, eDate)
        if not result.empty:
            # اگر بر‌اساس شماره درخواست است تعداد گردش های مادر را حساب میکنیم و بعد که کلیک شد فقط یکی از بچه ها را نشان می دهیم
            if reportBase == 'requestNo':
                result = result.drop_duplicates(subset=['previousInstanceId'], keep='last')

            result2 = result.groupby("OmoorCode").agg({"instanceId": 'nunique'}).reset_index()
            result2["instances"] = ""
            result2.rename(columns={"instanceId": "Count"}, inplace=True)
            result2 = result2[["OmoorCode", "Count", "instances"]]

            for row in result2.values.tolist():
                s = row[0]
                instance_list = result[result["OmoorCode"] == s]['instanceId'].tolist()
                concated_instance_list = ','.join(str(e) for e in instance_list)
                result2.loc[result2["OmoorCode"] == s, "instances"] = concated_instance_list

        if result.empty:
            query = """ SELECT "OmoorCode", 0 as "Count", '0' as "instances"
                                     FROM public."DW_Omoor" """
            if omoor == 0:
                result2 = pd.read_sql(query, connection, params=())
            else:
                result2 = pd.read_sql(query + """ where "OmoorCode"= %s """, connection, params=(omoor,))

        sum_row = {'OmoorCode': '0', 'Count': result2["Count"].sum(), 'instances': ''}
        result2 = result2.append(sum_row, ignore_index=True)

        return result2

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# نمونه گردش هایی که در یک بازه‌ی خاص شروع شده اند ولی در آن بازه تمام نشده اند برای گزارش تجمیعی
# اگر یک گردش چند بار به یک مرحله برود ما تمام آن دفعات را حساب میکنیم
def get_instance_count_accumulative(stateId, process, sDate, eDate, omoor, source, reportBase):
    connection = get_postgresql_connection()
    try:
        statesId = tuple(stateId.split(","))
        process = tuple(process.split(","))
        omoor = int(omoor)

        if source == '4':
            query = """ select "OmoorCode", "States".id as "instanceId", "previousInstanceId"
                                from "BPM".instance inner join "BPM"."States" 
                                on "BPM".instance."id" = "BPM"."States"."instanceId" and
                                "stateId" in %s and                                
                                date("stateStartDate") between %s and %s and
                                (("stateEndDate" is not NULL and "stateEndDate" > %s) or "stateEndDate" is NULL) 
                                and  "BPM".instance."statusType"=1 and "processId" in %s                           
                                join  "BPM"."Process" p  on p.id="BPM".instance."processId" 
                                inner join "BPM"."ControlProjectDetails" cp on "BPM".instance."id"= cp."instanceId" and "sourceId"=4  
                                inner join "BPM"."EngineeringDetails" ed on ed."documentNo"=cp."documentNo" 
                                inner join public."DW_Omoor" 
                                on ed."cityId"= public."DW_Omoor"."OmoorCode"                                                            
                                 """
            if omoor == 0:
                result = pd.read_sql(query, connection,
                                     params=(statesId, sDate, eDate, eDate, process,))
            else:
                result = pd.read_sql(query + """ and "OmoorCode"=%s  """,
                                     connection, params=(statesId, sDate, eDate, eDate, process, omoor,))
        else:
            query = """ select "OmoorCode", "States".id as "instanceId", "previousInstanceId"
                                from "BPM".instance inner join "BPM"."States" 
                                on "BPM".instance."id" = "BPM"."States"."instanceId" 
                                and "stateId" in %s                                
                                and date("stateStartDate") between %s and %s and
                                (("stateEndDate" is not NULL and "stateEndDate" > %s) or "stateEndDate" is NULL) 
                                and "BPM".instance."statusType"=1
                                and "processId" in %s 
                                inner join public."DW_Omoor" 
                                on "BPM".instance."unitId" = public."DW_Omoor"."OmoorCode"                                                                 
                                 """
            if omoor == 0:
                result = pd.read_sql(query, connection,
                                     params=(statesId, sDate, eDate, eDate, process,))
            else:
                result = pd.read_sql(query + """ and "OmoorCode"=%s 
                                                 """, connection,
                                     params=(statesId, sDate, eDate, eDate, process, omoor,))
        if not result.empty:
            # اگر بر‌اساس شماره درخواست است تعداد گردش های مادر را حساب میکنیم و بعد که کلیک شد فقط یکی از بچه ها را نشان می دهیم
            if reportBase == 'requestNo':
                result = result.drop_duplicates(subset=['previousInstanceId'], keep='last')

            result2 = result.groupby("OmoorCode").agg({"instanceId": 'nunique'}).reset_index()
            result2["instances"] = ""
            result2.rename(columns={"instanceId": "Count"}, inplace=True)
            result2 = result2[["OmoorCode", "Count", "instances"]]

            for row in result2.values.tolist():
                s = row[0]
                instance_list = result[result["OmoorCode"] == s]['instanceId'].tolist()
                concated_instance_list = ','.join(str(e) for e in instance_list)
                result2.loc[result2["OmoorCode"] == s, "instances"] = concated_instance_list

        if result.empty:
            query = """ SELECT "OmoorCode", 0 as "Count", '0' as "instances"
                                     FROM public."DW_Omoor" """
            if omoor == 0:
                result2 = pd.read_sql(query, connection, params=())
            else:
                result2 = pd.read_sql(query + """ where "OmoorCode"= %s """, connection, params=(omoor,))

        sum_row = {'OmoorCode': '0', 'Count': result2["Count"].sum(), 'instances': ''}
        result2 = result2.append(sum_row, ignore_index=True)
        return result2

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# ساختن دیتافریم برای ۴ بازه ی هر مرحله
def build_dataframe(parameter_list):
    from_date, to_date, item, report_type, selected_process, selected_omoor, source, i, reportBase = parameter_list
    start_date = shamsi_to_gregorian(from_date[item])
    end_date = shamsi_to_gregorian(to_date[item])
    # p = time.time()
    if report_type == "commonStatesReportOld":  # غیر تجمیعی
        df_item = get_instance_count(i, selected_process, start_date, end_date, selected_omoor, reportBase)
    else:  # تجمیعی
        df_item = get_instance_count_accumulative(i, selected_process, start_date, end_date, selected_omoor, source,
                                                  reportBase)
    # print("query: "+str(time.time() - p))
    df_item.rename(columns={"Count": "Count" + str(item + 1),
                            "instances": "instances" + str(item + 1)}, inplace=True)
    return df_item


# ساختن جدول و رت جیسون نهایی برای هر مرحله
def build_final_ret_json(parameter_list):
    from_date, to_date, report_type, selected_process, selected_omoor, source, ret_json, period_No, input_params, color_list, reportBase, i = parameter_list

    if report_type == "statesReport":
        state_name = get_state_name(i)
    if report_type in ("commonStatesReport", "commonStatesReportOld"):
        state_name = get_commonState_name(i)
        sub_states_list = get_states_common(i)
        converted_list = [str(element) for element in sub_states_list]
        i = ",".join(converted_list)

    pool = multiprocessing.Pool(4)

    # p = time.time()
    parameter_list = [[from_date, to_date, item, report_type, selected_process, selected_omoor, source, i, reportBase]
                      for
                      item in range(int(period_No))]
    df_list = pool.map(build_dataframe, parameter_list)
    # print("child process: "+str(time.time() - p))
    # The following is not really needed, since the (daemon) workers of the
    # child's pool are killed when the child is terminated, but it's good
    # practice to cleanup after ourselves anyway.
    pool.close()
    pool.join()

    df_list.append(get_cities_codes(selected_omoor))
    df = reduce(lambda df1, df2: pd.merge(df1, df2, on="OmoorCode", how="outer"), df_list)
    # df = df.merge(get_cities_codes(), on="OmoorCode", how="inner")
    df = df.where(pd.notnull(df), '0')
    df.loc[df["OmoorCode"] == '0', "OmoorName"] = 'مجموع'
    df["stateId"] = i

    columns_info = [{"type": 'text', "isShow": True}, {"type": 'text', "isShow": False},
                    {"type": 'text', "isShow": False}, {"type": 'text', "isShow": True}]

    # اضافه کردن ستون مجموع و ردیف مجموع
    df["Sum"] = 0
    sum_row_columns = ["row_numbers", "OmoorName"]
    columns = ["row_numbers", "stateId", "OmoorCode", "OmoorName"]
    persian_columns = ['ردیف', 'کد مرحله', 'کد شهرستان', 'شهرستان']

    for item in range(int(period_No), 0, -1):
        column_name = "Count" + str(item)
        column_color = "Count" + str(item) + "-color"
        column_name_instance = "instances" + str(item)

        df[column_name] = df[column_name].astype(int)
        df[column_name_instance] = df[column_name_instance].astype(str)
        df['Sum'] = df['Sum'] + df[column_name]
        df[column_color] = df[column_name].apply(lambda x: {"color": color_list[item], "value": str(x)})
        sum_row_columns.append(column_name)

        columns_info.append({"type": 'button', "isShow": False})
        columns_info.append({"type": 'text-color', "isShow": True})
        columns_info.append({"type": 'text', "isShow": False})

        columns.append(column_name)
        columns.append(column_color)
        columns.append(column_name_instance)

        if report_type in ("commonStatesReport", "statesReport"):  # عنوان ستون برای تجمیعی ها
            if item == int(period_No):  # اگر این بازه کوچکترین بازه است
                _date = 'تعداد تجمیعی درخواستهای انجام نشده  ' + 'از تاریخ ' + from_date[
                    item - 1] + ' تا تاریخ ' + to_date[item - 1]
            else:
                _date = 'تعداد تجمیعی درخواستهای انجام نشده  ' + ' تا تاریخ ' + to_date[item - 1]
        else:  # عنوان ستون برای غیر تجمیعی
            _date = 'تعداد درخواستهای انجام نشده  ' + 'از تاریخ ' + from_date[item - 1] + ' تا تاریخ ' + \
                    to_date[item - 1]

        persian_columns.append('تعداد درخواست ' + str(item))
        persian_columns.append(_date)
        persian_columns.append('نمونه های ' + str(item))

    df["Sum"] = df["Sum"].apply(lambda x: {"color": '#a9a9a9', "value": str(x)})

    if report_type == "commonStatesReportOld":  # غیر تجمیعی
        # محاسبه ی مقدار ردیف "مجموع" برای ستون "مجموع" برای غیر تجمیعی ها که در تجمیعی ها نیازی نیست چون
        # ستون مجموع را نداریم درواقع محاسبه ی سلولی است که در تقاطع ستون آخر و ردیف آخر میباشد
        df.loc[df["OmoorCode"] == '0', "Sum"] = [d.get('value') for d in df.loc[df["OmoorCode"] == '0', "Sum"]]
        sum_row_columns.append("Sum")

    df["row_numbers"] = ''
    df.loc[df["OmoorCode"] == '0', "row_numbers"] = len(df)
    sum_row = df[df["OmoorCode"] == '0'][sum_row_columns].values.tolist()

    columns.append("Sum")
    persian_columns.append('مجموع')
    sum_flag = False
    if report_type == "commonStatesReportOld":
        sum_flag = True
    columns_info.append({"type": 'text-color', "isShow": sum_flag})

    df = df.drop(df[df["OmoorCode"] == '0'].index)
    df = df.sort_values(by="OmoorName")
    df["row_numbers"] = numpy.arange(start=1, stop=len(df) + 1)
    df = df[columns]
    df = df.to_dict(orient='split')
    df = df["data"]

    if report_type == "commonStatesReportOld":  # آنکلیک جدول، غیرتجمیعی نمودار استک ندارد
        inner = [
            {
                'column': '@Count1-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances1"},
                'type': 'process',
                "method": "post"
            },
            {
                'column': '@Count2-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances2"},
                'type': 'process',
                "method": "post"
            },
            {
                'column': '@Count3-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances3"},
                'type': 'process',
                "method": "post"
            },
            {
                'column': '@Count4-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances4"},
                'type': 'process',
                "method": "post"
            }
        ]
    else:
        inner = [
            {
                'column': '@Count1-color',
                'indicatorid': '6018',
                "showModal": False,
                'params': {"instances1": "@instances1",
                           "instances2": "@instances2",
                           "instances3": "@instances3",
                           "instances4": "@instances4",
                           "OmoorCode": "@OmoorCode",
                           "stateId": "@stateId",
                           **input_params},
                'type': 'statesReport',
                "method": "post"
            },
            {
                'column': '@Count1-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances1"},
                'type': 'process',
                "method": "post"
            },
            {
                'column': '@Count2-color',
                'indicatorid': '6018',
                "showModal": False,
                'params': {"instances2": "@instances2",
                           "instances3": "@instances3",
                           "instances4": "@instances4",
                           "OmoorCode": "@OmoorCode",
                           "stateId": "@stateId",
                           **input_params},
                'type': 'statesReport',
                "method": "post"
            },
            {
                'column': '@Count2-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances2"},
                'type': 'process',
                "method": "post"
            },
            {
                'column': '@Count3-color',
                'indicatorid': '6018',
                "showModal": False,
                'params': {"instances3": "@instances3",
                           "instances4": "@instances4",
                           "OmoorCode": "@OmoorCode",
                           "stateId": "@stateId",
                           **input_params},
                'type': 'statesReport',
                "method": "post"
            },
            {
                'column': '@Count3-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances3"},
                'type': 'process',
                "method": "post"
            },
            {
                'column': '@Count4-color',
                'indicatorid': '6018',
                "showModal": False,
                'params': {"instances4": "@instances4",
                           "OmoorCode": "@OmoorCode",
                           "stateId": "@stateId",
                           **input_params},
                'type': 'statesReport',
                "method": "post"
            },
            {
                'column': '@Count4-color',
                'indicatorid': '6016',
                "showModal": False,
                'params': {"instances": "@instances4"},
                'type': 'process',
                "method": "post"
            }
        ]

    data = {
        "export": [{"default": True, "persian_name": "خروجی اکسل", "type": "excel"}],
        "type": "joined",
        "groupid": 0,
        "title": "table" + i,
        "persian_title": state_name,
        "rowcount": len(df),
        "columns": columns,
        "data": df,
        "paging": False,
        "persian_columns": persian_columns,
        'columns_info': columns_info,
        'footer': sum_row,
        "onclick": {
            "oncell": {
                "inner": inner
            }
        },
    }

    return data


# نمونه گردش هایی که در یک بازه‌ی خاص انجام و تمام شده اند
def done_preInstances(sDate, eDate, instances):
    connection = get_postgresql_connection()
    try:
        instances = tuple(instances)

        result = pd.read_sql(""" SELECT "instanceId" FROM "BPM"."States" where id IN %s and 
                                 "stateEndDate" is not NULL and date("stateEndDate") between %s and %s """,
                             connection, params=(instances, sDate, eDate,))
        if result.empty:
            return []
        else:
            return result["instanceId"].values.tolist()

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# نمونه گردش هایی که در یک بازه‌ی خاص انجام(تمام) نشده اند
def notdone_preInstances(eDate, instances):
    connection = get_postgresql_connection()
    try:
        instances = tuple(instances)

        result = pd.read_sql(""" SELECT "instanceId" FROM "BPM"."States" where id IN %s and 
                            (("stateEndDate" is not NULL and "stateEndDate" > %s) or "stateEndDate" is NULL) """,
                             connection, params=(instances, eDate,))
        if result.empty:
            return []
        else:
            return result["instanceId"].values.tolist()

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# نمونه گردش هایی که از یک بازه‌ی خاص شروع شده اند و در همان بازه هم تمام شده اند
def new_instances_done(stateId, process, sDate, eDate, omoor, source):
    connection = get_postgresql_connection()
    try:
        process = tuple(process.split(","))
        omoor = int(omoor)

        if source == '4':
            result = pd.read_sql(""" select "States"."instanceId"
                                                from "BPM".instance inner join "BPM"."States"
                                                on "BPM".instance."id" = "BPM"."States"."instanceId"
                                                and "stateId" in %s 
                                                and "BPM".instance."statusType"=1
                                                and "processId" in %s and date("stateStartDate") between %s and %s
                                                and date("stateEndDate") between %s and %s
                                                join  "BPM"."Process" p on p.id="BPM".instance."processId"
                                                inner join "BPM"."ControlProjectDetails" cp on "BPM".instance."id"= cp."instanceId" and "sourceId"=4
                                                inner join "BPM"."EngineeringDetails" ed on ed."documentNo"=cp."documentNo"
                                                inner join public."DW_Omoor" 
                                                on ed."cityId"= public."DW_Omoor"."OmoorCode"                                                
                                                and "OmoorCode"=%s
                                                 """, connection,
                                 params=(stateId, process, sDate, eDate, sDate, eDate, omoor,))
        else:
            result = pd.read_sql(""" select "instanceId"
                                                from "BPM".instance inner join "BPM"."States"
                                                on "BPM".instance."id" = "BPM"."States"."instanceId" 
                                                and "stateId" in %s
                                                and "BPM".instance."statusType"=1
                                                and "processId" in %s and date("stateStartDate") between %s and %s
                                                and date("stateEndDate") between %s and %s
                                                inner join public."DW_Omoor"
                                                on "BPM".instance."unitId" = public."DW_Omoor"."OmoorCode"                                                                                            
                                                and "OmoorCode"=%s
                                                 """, connection,
                                 params=(stateId, process, sDate, eDate, sDate, eDate, omoor,))

        if result.empty:
            return []
        else:
            return result["instanceId"].values.tolist()

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# نمونه گردش هایی که در یک بازه‌ی خاص شروع شده اند ولی در همان بازه تمام نشده اند
def new_instances_notdone(stateId, process, sDate, eDate, omoor, source):
    connection = get_postgresql_connection()
    try:

        process = tuple(process.split(","))
        omoor = int(omoor)

        if source == '4':
            result = pd.read_sql(""" SELECT "States"."instanceId"
                                                FROM "BPM".instance inner join "BPM"."States"
                                                on "BPM".instance."id" = "BPM"."States"."instanceId" 
                                                and "stateId" in %s                                       
                                                and date("stateStartDate") between %s and %s
                                                and (("stateEndDate" is not NULL and "stateEndDate" > %s) or "stateEndDate" is NULL)                                       
                                                and "BPM".instance."statusType"=1 and "processId" in %s
                                                inner join "BPM"."Process" p on p.id="BPM".instance."processId" 
                                                inner join "BPM"."ControlProjectDetails" cp on "BPM".instance."id"= cp."instanceId" and "sourceId"=4  
                                                inner join "BPM"."EngineeringDetails" ed on ed."documentNo"=cp."documentNo" 
                                                inner join public."DW_Omoor" 
                                                on ed."cityId"= public."DW_Omoor"."OmoorCode"                                                
                                                and "OmoorCode"=%s 
                                                 """, connection,
                                 params=(stateId, sDate, eDate, eDate, process, omoor,))
        else:
            result = pd.read_sql(""" SELECT "instanceId"
                                                FROM "BPM".instance inner join "BPM"."States" 
                                                on "BPM".instance."id" = "BPM"."States"."instanceId"
                                                and "stateId" in %s                                               
                                                and date("stateStartDate") between %s and %s  
                                                and (("stateEndDate" is not NULL and "stateEndDate" > %s) or "stateEndDate" is NULL)                                                 
                                                and "BPM".instance."statusType"=1 and "processId" in %s 
                                                inner join public."DW_Omoor" 
                                                on "BPM".instance."unitId" = public."DW_Omoor"."OmoorCode"                                                 
                                                and "OmoorCode"=%s 
                                                 """, connection,
                                 params=(stateId, sDate, eDate, eDate, process, omoor,))

        if result.empty:
            return []
        else:
            return result["instanceId"].values.tolist()

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# اقدامات انجام شده روی این فرآیند
def get_related_instances(persuitCodeInstanceId):
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql(""" SELECT "BPM".instance.id as "instanceId","BPM"."States".id as "sid",
                                    "BPM"."States"."stateId", 
                                      "processStartDate", '' as "stateName"
                                        FROM "BPM".instance inner join "BPM"."States"
                                        on "BPM".instance."id" = "BPM"."States"."instanceId"
                                        where "processId"=%s and "previousInstanceId"=%s
                                         """, connection,
                             params=(5643, int(persuitCodeInstanceId),))

        if not result.empty:
            result = result.groupby("instanceId").agg(
                {"sid": 'max', "stateId": 'max', "processStartDate": 'min'}).reset_index()

        result["processStartDate"] = result["processStartDate"].apply(get_shamsi_date)
        result.loc[result["stateId"] == 230984, "stateName"] = 'کارشناس بصیر'
        result.loc[result["stateId"] == 230985, "stateName"] = 'کارشناس ستاد'
        result.loc[result["stateId"] == 230986, "stateName"] = 'امور شهرستان'
        result.loc[result["stateId"] == 237291, "stateName"] = 'فرآیند خاتمه یافته است'

        result = result[["instanceId", "sid", "stateId", "stateName", "processStartDate"]]

        return result

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# بدست آوردن یونیت آی دی این فرآیند
def get_unit_of_instance(persuitCode):
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql("""select id, "unitId" from "BPM".instance where "sourceInstanceid"=%s """,
                             connection, params=(persuitCode,))

        unitId = result.iloc[0]["unitId"]
        instanceId = result.iloc[0]["id"]
        return unitId, instanceId

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# بدست آوردن رکورد دیتیل برای پر کردن تبهای قبلا پر شده
def get_details_info(instanceId, statesId):
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql("""SELECT "stateInfo" FROM "BPM"."StateInfoDetails" 
                                where "instanceId"=%s and "stateInfo"->>'stateId'=%s """,
                             connection, params=(instanceId, statesId,))
        return result["stateInfo"].loc[0]

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# لیست عارضه
def get_reason():
    connection = get_postgresql_connection()
    try:
        result = pd.read_sql("""SELECT "Id", "reasonName" FROM "BPM"."ReasonType" order by "reasonName" """,
                             connection, params=())

        reason_list = []
        for i in result.values.tolist():
            reason_list += {"key": i[0], "value": i[1]},
        return reason_list

    except Exception as ex:
        print(str(ex))
        return None
    finally:
        if connection is not None:
            connection.close()


# جدول تعداد فرآیندها
@app.route('/statesReport', methods=['GET'])  # indicatorId: 6017
@token_required
def statesReport(user):
    # Indicator Id = 6017    Type = statesReport
    input_params = clear_input_params(request.args)
    from_date_default1, to_date_default1 = get_default_date(period=7)
    from_date_default2 = get_default_enddate(period=14)
    from_date_default3 = get_default_enddate(period=21)
    from_date_default4 = '1400/01/01'

    omoor = OmoorCombo()

    process_data = [{"key": "0", "value": "انتخاب کنید"}]
    if input_params.get("source", False):
        selected_source = request.args['source']
        process_data += get_process(selected_source)

    states_data = []
    if input_params.get("process", False):
        selected_process = request.args['process']
        states_data += get_states_combo(int(selected_process))

    processes_data = [{"key": "0", "value": "انتخاب کنید"}]
    if input_params.get("commonstates", False):
        selected_commonstates = request.args['commonstates']
        processes_data += get_processes(selected_commonstates)

    chart_filters = [{"type": "filter",
                      "data": [
                          {
                              "type": "groupSelector",
                              "param": "report_type",
                              "data": {
                                  "commonStatesReportOld": "گزارش غیرتجمیعی - مراحل منتخب",
                                  "commonStatesReport": "گزارش تجمیعی - مراحل منتخب",
                                  "statesReport": "گزارش تجمیعی - فرآیند محور",

                              },
                              "default_value": input_params.get("report_type", "commonStatesReportOld"),
                              "label": "نوع گزارش",
                              "className": "col-md-3",
                              "groupBox": 'Top'
                          },
                          {
                              "type": "combo2",
                              "param": "reportBase",
                              "data": [{"key": "trackingNo", "value": "بر‌اساس شماره پیگیری"},
                                       {"key": "requestNo", "value": "بر‌اساس شماره درخواست"}],
                              "default_value": input_params.get("reportBase", "requestNo"),
                              "label": "نمایش",
                              "className": "col-md-3",
                              "groupBox": 'Top',
                          },
                          {
                              "type": "combo2",
                              "param": "source",
                              "data": get_source(),
                              "default_value": input_params.get("source", "0"),
                              "label": "حوزه",
                              "groupBox": 0,
                              "groupId": ["statesReport"],
                              "onSelect": {"param": "process", "type": "combo", "indicatorid": "1113"}
                          },
                          {
                              "type": "dropdown",
                              "param": "omoor",
                              "data": omoor,
                              "default_value": input_params.get("omoor", "0"),
                              "label": "شهرستان",
                              "groupId": ["statesReport", "commonStatesReport", "commonStatesReportOld"],
                              "className": "col-md-2",
                              "groupBox": 0
                          },
                          {
                              "type": "dropdown",
                              "param": "process",
                              "data": process_data,
                              "default_value": input_params.get("process", "0"),
                              "label": "فرآیند",
                              "groupBox": 0,
                              "groupId": ["statesReport"],
                              "onSelect": {"param": "states", "type": "combo", "indicatorid": "1112"}
                          },
                          {
                              "type": "multiselect2",
                              "param": "states",
                              "data": states_data,
                              "default_value": input_params.get("states", ""),
                              "label": "مراحل",
                              "groupId": ["statesReport"],
                              "groupBox": 0
                          },
                          {
                              "type": "multiselect2",
                              "param": "commonstates",
                              "data": get_states_common_combo(),
                              "default_value": input_params.get("commonstates", ""),
                              "label": "مراحل",
                              "groupId": ["commonStatesReport", "commonStatesReportOld"],
                              "groupBox": 0,
                              "onSelect": {"param": "processes", "type": "combo", "indicatorid": "1124"}
                          },
                          {
                              "type": "multiselect2",
                              "param": "processes",
                              "data": processes_data,
                              "default_value": input_params.get("processes", ""),
                              "label": "فرآیند",
                              "groupBox": 0,
                              "groupId": ["commonStatesReport", "commonStatesReportOld"],
                          },
                          {
                              "type": "groupSelector",
                              "param": "period_No",
                              "data": {
                                  "1": "یک",
                                  "2": "دو",
                                  "3": "سه",
                                  "4": "چهار",
                              },
                              "default_value": input_params.get("period_No", "4"),
                              "label": "تعداد بازه",
                              "className": "col-md-1",
                              "groupId": ["statesReport", "commonStatesReport", "commonStatesReportOld"],
                              "groupBox": 0
                          },
                          {
                              "type": "date",
                              "param": "from_date1",
                              "default_value": input_params.get("from_date1", from_date_default1),
                              "label": "تاریخ شروع",
                              "groupBox": 1,
                              "groupId": ["1", "2", "3", "4"]
                          },
                          {
                              "type": "date",
                              "param": "to_date1",
                              "default_value": input_params.get("to_date1", to_date_default1),
                              "label": "تاریخ پایان",
                              "groupBox": 1,
                              "groupId": ["1", "2", "3", "4"]
                          },
                          {
                              "type": "color-picker",
                              "param": "color1",
                              "default_value": "#" + input_params.get("color1", "B4F8C8"),
                              "label": "انتخاب رنگ",
                              "groupBox": 1,
                              "className": "col-md-1",
                              "groupId": ["1", "2", "3", "4"]
                          },
                          {
                              "type": "date",
                              "param": "from_date2",
                              "default_value": input_params.get("from_date2", from_date_default2),
                              "label": "تاریخ شروع",
                              "groupBox": 2,
                              "groupId": ["2", "3", "4"]
                          },
                          {
                              "type": "date",
                              "param": "to_date2",
                              "default_value": input_params.get("to_date2", from_date_default1),
                              "label": "تاریخ پایان",
                              "groupBox": 2,
                              "groupId": ["2", "3", "4"]
                          },
                          {
                              "type": "color-picker",
                              "param": "color2",
                              "default_value": "#" + input_params.get("color2", "91B8D9"),
                              "label": "انتخاب رنگ",
                              "groupBox": 2,
                              "className": "col-md-1",
                              "groupId": ["2", "3", "4"]
                          },
                          {
                              "type": "date",
                              "param": "from_date3",
                              "default_value": input_params.get("from_date3", from_date_default3),
                              "label": "تاریخ شروع",
                              "groupBox": 3,
                              "groupId": ["3", "4"]
                          },
                          {
                              "type": "date",
                              "param": "to_date3",
                              "default_value": input_params.get("to_date3", from_date_default2),
                              "label": "تاریخ پایان",
                              "groupBox": 3,
                              "groupId": ["3", "4"]
                          },
                          {
                              "type": "color-picker",
                              "param": "color3",
                              "default_value": "#" + input_params.get("color3", "EEBE35"),
                              "label": "انتخاب رنگ",
                              "groupBox": 3,
                              "className": "col-md-1",
                              "groupId": ["3", "4"]
                          },
                          {
                              "type": "date",
                              "param": "from_date4",
                              "default_value": input_params.get("from_date4", from_date_default4),
                              "label": "تاریخ شروع",
                              "groupBox": 4,
                              "groupId": ["4"]
                          },
                          {
                              "type": "date",
                              "param": "to_date4",
                              "default_value": input_params.get("to_date4", from_date_default3),
                              "label": "تاریخ پایان",
                              "groupBox": 4,
                              "groupId": ["4"]
                          },
                          {
                              "type": "color-picker",
                              "param": "color4",
                              "default_value": "#" + input_params.get("color4", "f53107"),
                              "label": "انتخاب رنگ",
                              "groupBox": 4,
                              "className": "col-md-1",
                              "groupId": ["4"]
                          }
                      ],
                      "onclick": [
                          {
                              "params": input_params,
                              "indicatorid": "6017",
                              "type": "statesReport",
                              "method": "get"
                          }
                      ]
                      }]

    try:
        # get input parameters
        report_type = input_params.get('report_type', "commonStatesReportOld")
        selected_omoor = input_params.get('omoor', "0")
        process = input_params.get('process', "0")
        processes = input_params.get('processes', "")
        reportBase = input_params.get('reportBase', "")

        if report_type == "statesReport":
            states = input_params.get('states', "")
        else:
            states = input_params.get('commonstates', "")
        selected_states_list = []
        if states != "":
            selected_states_list = tuple(states.split(","))
            if report_type == 'commonStatesReportOld' and len(selected_states_list) > 1:
                selected_states_list += (states.split(","),)

        source = input_params.get('source', "0")
        period_No = input_params.get('period_No', "4")
        color1 = "#" + input_params.get('color1', "B4F8C8")
        color2 = "#" + input_params.get('color2', "91B8D9")
        color3 = "#" + input_params.get('color3', "EEBE35")
        color4 = "#" + input_params.get('color4', "f53107")
        color_list = [None, color1, color2, color3, color4]

        from_date1 = input_params.get('from_date1', from_date_default1)
        to_date1 = input_params.get('to_date1', to_date_default1)
        from_date2 = input_params.get('from_date2', from_date_default2)
        to_date2 = input_params.get('to_date2', from_date_default1)
        from_date3 = input_params.get('from_date3', from_date_default3)
        to_date3 = input_params.get('to_date3', from_date_default2)
        from_date4 = input_params.get('from_date4', from_date_default4)
        to_date4 = input_params.get("to_date4", get_default_enddate(period=22))

        from_date = [from_date1, from_date2, from_date3, from_date4]
        to_date = [to_date1, to_date2, to_date3, to_date4]

        # برای محاسبه ی تجمیعی داده ها ابتدای همه‌ی بازه ها را تاریخ شروع کوچکترین بازه‌ي انتخابی در نظر میگیریم
        if report_type in ("statesReport", "commonStatesReport"):
            from_date = [from_date[int(period_No) - 1] for i in range(int(period_No))]

        if report_type == "statesReport" and source == "0" and len(input_params) != 1:
            ret_json = error_message('حوزه موردنظر را انتخاب نمایید.', chart_filters)
            return jsonify(ret_json), 400

        if report_type == "statesReport" and process == "0" and len(input_params) != 1:
            ret_json = error_message('فرآیند موردنظر را انتخاب نمایید.', chart_filters)
            return jsonify(ret_json), 400

        if states == "" and len(input_params) != 1:
            ret_json = error_message('مراحل موردنظر را انتخاب نمایید.', chart_filters)
            return jsonify(ret_json), 400

        if report_type in ("commonStatesReportOld", "commonStatesReport") \
                and processes == "" and len(input_params) != 1:
            ret_json = error_message('فرآیندهای موردنظر را انتخاب نمایید.', chart_filters)
            return jsonify(ret_json), 400

        if len(input_params) != 1:
            from_date_persian = ["تاریخ شروع بازه‌ی اول", "تاریخ شروع بازه‌ی دوم", "تاریخ شروع بازه‌ی سوم",
                                 "تاریخ شروع بازه‌ی چهارم"]
            to_date_persian = ["تاریخ پایان بازه‌ی اول", "تاریخ پایان بازه‌ی دوم", "تاریخ پایان بازه‌ی سوم",
                               "تاریخ شروع پایان چهارم"]
            for i in range(int(period_No)):
                error = date_validation(from_date[i], from_date_persian[i])
                if error != '':
                    ret_json = error_message(error, chart_filters)
                    return jsonify(ret_json), 400
                error = date_validation(to_date[i], to_date_persian[i])
                if error != '':
                    ret_json = error_message(error, chart_filters)
                    return jsonify(ret_json), 400

                error = period_validation(from_date[i], to_date[i])
                if error != '':
                    ret_json = error_message(error, chart_filters)
                    return jsonify(ret_json), 400

        if report_type in ("commonStatesReportOld", "commonStatesReport"):
            selected_process = processes
        else:
            selected_process = process

        ret_json = []
        ret_json += chart_filters.copy()
        ret_json += [{"type": "rich-table",
                      "data": []
                      }]
        if len(input_params) == 1:
            pool = MyPool(1)
        else:
            pool = MyPool(len(selected_states_list))

        # p = time.time()
        parameter_list = [
            [from_date, to_date, report_type, selected_process, selected_omoor, source, ret_json, period_No,
             input_params, color_list, reportBase, i] for
            i in selected_states_list]
        ret_json[1]["data"] = pool.map(build_final_ret_json, parameter_list)
        pool.close()
        pool.join()
        # print("parent process: "+str(time.time() - p))

        return jsonify(ret_json), 200

    except Exception as e:
        print(e)
        return jsonify({'title': 'خطا', 'message': 'خطایی رخ داده است'}), 500


# نمودار استک
@app.route('/stackedChart', methods=['POST'])  # indicatorId: 6018
@token_required
def stackedChart(user):
    # Indicator Id = 6018    Type = statesReport

    input_params = clear_input_params(request.get_json())
    omoor = input_params.get("OmoorCode", '0')
    source = input_params.get("source", '0')
    states = input_params.get('stateId', "")
    selected_states_list = tuple(states.split(","))
    report_type = input_params.get('report_type', "")

    if report_type in ("commonStatesReportOld", "commonStatesReport"):
        selected_process = input_params.get('processes', "")
    else:
        selected_process = input_params.get('process', "")

    if input_params.get("instances1", False):
        instances1 = input_params.get("instances1")
        if instances1 == "0":
            instances1 = []
        else:
            instances1 = instances1.split(',')
        from_date1 = input_params.get("from_date1", '')
        to_date1 = input_params.get("to_date1", '')
        _priod1 = 'از تاریخ ' + from_date1 + 'تا تاریخ ' + to_date1
        from_date1 = jdatetime.datetime.strptime(from_date1, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")
        to_date1 = jdatetime.datetime.strptime(to_date1, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")

    if input_params.get("instances2", False):
        instances2 = input_params.get("instances2")
        if instances2 == "0":
            instances2 = []
        else:
            instances2 = instances2.split(',')
        from_date2 = input_params.get("from_date2", '')
        to_date2 = input_params.get("to_date2", '')
        _priod2 = 'از تاریخ ' + from_date2 + 'تا تاریخ ' + to_date2
        from_date2 = jdatetime.datetime.strptime(from_date2, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")
        to_date2 = jdatetime.datetime.strptime(to_date2, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")

    if input_params.get("instances3", False):
        instances3 = input_params.get("instances3")
        if instances3 == "0":
            instances3 = []
        else:
            instances3 = instances3.split(',')
        from_date3 = input_params.get("from_date3", '')
        to_date3 = input_params.get("to_date3", '')
        _priod3 = 'از تاریخ ' + from_date3 + 'تا تاریخ ' + to_date3
        from_date3 = jdatetime.datetime.strptime(from_date3, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")
        to_date3 = jdatetime.datetime.strptime(to_date3, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")

    if input_params.get("instances4", False):
        instances4 = input_params.get("instances4")
        if instances4 == "0":
            instances4 = []
        else:
            instances4 = instances4.split(',')
        from_date4 = input_params.get("from_date4", '')
        to_date4 = input_params.get("to_date4", '')
        _priod4 = 'از تاریخ ' + from_date4 + 'تا تاریخ ' + to_date4
        from_date4 = jdatetime.datetime.strptime(from_date4, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")
        to_date4 = jdatetime.datetime.strptime(to_date4, "%Y/%m/%d").togregorian().strftime("%Y-%m-%d")

    df = pd.DataFrame(columns=('priod', 'preWeek_done', 'preWeek_notdone', 'new_done', 'new_notdone'))

    if input_params.get("instances4", False):
        # گردش هایی که در این بازه شروع و در همین بازه تمام شده اند
        new_instances4_done = new_instances_done(selected_states_list, selected_process, from_date4, to_date4, omoor,
                                                 source)
        # گردش هایی که در این بازه شروع ولی در همین بازه تمام نشده اند
        new_instances4_notdone = new_instances_notdone(selected_states_list, selected_process, from_date4, to_date4,
                                                       omoor, source)
        row4 = ['وضعیت درخواست ها ' + _priod4, 0, 0, len(new_instances4_done), len(new_instances4_notdone)]
        df.loc[len(df)] = row4

    if input_params.get("instances3", False):
        if len(instances4) == 0:
            notdone_instances3_preWeek = []
            done_instances3_preWeek = []
        else:
            notdone_instances3_preWeek = notdone_preInstances(to_date3, instances4)
            done_instances3_preWeek = done_preInstances(from_date3, to_date3, instances4)
        new_instances3_done = new_instances_done(selected_states_list, selected_process, from_date3, to_date3, omoor,
                                                 source)
        new_instances3_notdone = new_instances_notdone(selected_states_list, selected_process, from_date3, to_date3,
                                                       omoor, source)
        # total_notdone_instances3 = notdone_instances3_preWeek + new_instances3
        row3 = ['وضعیت درخواست ها ' + _priod3, len(done_instances3_preWeek), len(notdone_instances3_preWeek),
                len(new_instances3_done), len(new_instances3_notdone)]
        df.loc[len(df)] = row3

    if input_params.get("instances2", False):
        if len(instances3) == 0:
            notdone_instances2_preWeek = []
            done_instances2_preWeek = []
        else:
            notdone_instances2_preWeek = notdone_preInstances(to_date2, instances3)
            done_instances2_preWeek = done_preInstances(from_date2, to_date2, instances3)
        new_instances2_done = new_instances_done(selected_states_list, selected_process, from_date2, to_date2, omoor,
                                                 source)
        new_instances2_notdone = new_instances_notdone(selected_states_list, selected_process, from_date2, to_date2,
                                                       omoor, source)
        # total_notdone_instances2 = notdone_instances2_preWeek + new_instances2
        row2 = ['وضعیت درخواست ها ' + _priod2, len(done_instances2_preWeek), len(notdone_instances2_preWeek),
                len(new_instances2_done), len(new_instances2_notdone)]
        df.loc[len(df)] = row2

    if input_params.get("instances1", False):
        if len(instances2) == 0:
            notdone_instances1_preWeek = []
            done_instances1_preWeek = []
        else:
            notdone_instances1_preWeek = notdone_preInstances(to_date1, instances2)
            done_instances1_preWeek = done_preInstances(from_date1, to_date1, instances2)
        new_instances1_done = new_instances_done(selected_states_list, selected_process, from_date1, to_date1, omoor,
                                                 source)
        new_instances1_notdone = new_instances_notdone(selected_states_list, selected_process, from_date1, to_date1,
                                                       omoor, source)
        row1 = ['وضعیت درخواست ها ' + _priod1, len(done_instances1_preWeek), len(notdone_instances1_preWeek),
                len(new_instances1_done), len(new_instances1_notdone)]
        df.loc[len(df)] = row1

    data_list = []
    categories_names = []
    color = ["#A7E336", "#B92B22", "#F3E604", '#F78E10']
    names = ["انجام شده‌ از بازه‌ی قبل", "انجام نشده‌ از بازه‌ی قبل",
             "نمونه های جدید این بازه که در همین بازه انجام شده اند",
             "نمونه های جدید این بازه که در این بازه انجام نشده اند"]

    for k in range(len(df)):
        categories_names.append(df['priod'][k])

    j = 0
    for i in names:
        data_list.append({
            "name": i,
            "data": df[df.columns.tolist()[j + 1]].values.tolist(),
            "color": color[j]
        })
        j += 1

    obj = sc.StakedColumnConvertor(data_series=data_list,
                                   categories_names=categories_names,
                                   base_json_path="package.json",
                                   title="وضعیت درخواست ها",
                                   subtitle="",
                                   yaxis_title='تعداد',
                                   xaxis_title='')

    ret_json = [{"type": "chart", "className": "col-md-12", "data": obj.convert_to_chart()}]
    return jsonify(ret_json), 200


# کمبوی فرآیند برای گزارش های مبنی بر فرآیند
@app.route("/process", methods=["GET"])  # indicatorId: 1113
def process():
    process_data = [{"key": "0", "value": "انتخاب کنید"}]
    selected_source = request.args['source']
    process_data += get_process(selected_source)

    filters = [
        {
            "type": "dropdown",
            "param": "process",
            "data": process_data,
            "default_value": request.args.get("process", "0"),
            "label": "فرآیند"
        }
    ]

    return jsonify(filters), 200


# مالتی سلکت مرحله
@app.route("/states", methods=["GET"])  # indicatorId: 1112
def states():
    processId = request.args['process']
    states_data = []
    states_data += get_states_combo(int(processId))

    filters = [
        {
            "type": "multiselect2",
            "param": 'states',
            "data": states_data,
            "default_value": request.args.get("states", ""),
            "label": "مراحل"
        }
    ]

    return jsonify(filters), 200


# مالتی سلکت فرآیند برای گزارش های مبنی بر مرحله
@app.route("/processes", methods=["GET"])  # indicatorId: 1124
def processes():
    commonstates = request.args['commonstates']
    processes_data = []
    processes_data += get_processes(commonstates)

    filters = [
        {
            "type": "multiselect2",
            "param": 'processes',
            "data": processes_data,
            "default_value": request.args.get("processes", ""),
            "label": "فرآیندها"
        }
    ]

    return jsonify(filters), 200


# سابقه ی فرآیندها
@app.route('/instancesHistory', methods=['GET'])  # indicatorId: 1121
@token_required
def instances(user):
    # Indicator Id = 1121    Type = statesReport
    input_params = clear_input_params(request.args)
    persuitCode = request.args["persuitCode"]

    try:
        unitId, previousInstanceId = get_unit_of_instance(persuitCode)
        df = get_related_instances(previousInstanceId)
        ret_json = []

        if not df.empty:
            df = df.to_dict(orient='split')
            ret_json = [{"type": "rich-table",
                         "data": [{
                             "export": [{"default": True, "persian_name": "خروجی اکسل", "type": "excel"}],
                             "type": "joined",
                             "groupid": 0,
                             "title": "tableHistory",
                             "persian_title": "سوابق فرآیندها",
                             "rowcount": len(df),
                             "columns": ["instanceId", "sid", "stateId", "stateName", "processStartDate"],
                             "data": df["data"],
                             "paging": True,
                             "persian_columns": ['شماره فرآیند', 'آی دی جدول استیت', 'شماره مرحله', 'نام مرحله',
                                                 'تاریخ شروع فرآیند'],
                             'columns_info': [{"type": 'button', "isShow": True}, {"type": 'text', "isShow": False},
                                              {"type": 'text', "isShow": False},
                                              {"type": 'text', "isShow": True}, {"type": 'text', "isShow": True}],
                             "onclick": {
                                 "oncell": {
                                     "inner": [{
                                         'column': '@instanceId',
                                         'indicatorid': '1114',
                                         "showModal": False,
                                         'params': {"instanceId": "@instanceId",
                                                    "stateId": "@stateId",
                                                    "sid": "@sid",
                                                    **input_params
                                                    },
                                         'type': 'statesReport',
                                         "method": "get"
                                     }]
                                 }
                             },
                         },
                         ]
                         }]

        df = pd.DataFrame(["ایجاد"], columns=["new"])
        df = df.to_dict(orient='split')
        ret_json += [{"type": "rich-table",
                      "data": [{
                          "export": [{"default": True, "persian_name": "خروجی اکسل", "type": "excel"}],
                          "type": "joined",
                          "groupid": 0,
                          "title": "tableHistory",
                          "persian_title": "ایجاد فرآیند جدید",
                          "rowcount": 1,
                          "columns": ["new"],
                          "data": df["data"],
                          "paging": True,
                          # "persian_columns": ['ایجاد فرآیند جدید'],
                          'columns_info': [{"type": 'button', "isShow": True}],
                          "onclick": {
                              "oncell": {
                                  "inner": [{
                                      'column': '@new',
                                      'indicatorid': '1114',
                                      "showModal": False,
                                      'params': request.args.to_dict(),
                                      'type': 'statesReport',
                                      "method": "get"
                                  }]
                              }
                          },
                      },
                      ]
                      }]

        return jsonify(ret_json), 200

    except Exception as e:
        print(e)
        return jsonify({'title': 'خطا', 'message': 'خطایی رخ داده است'}), 500


# تبهای فرم
@app.route("/forms/menu", methods=["GET"])  # indicatorId: 1114
def forms_menu():
    # Indicator Id = 1114     Type = statesReport
    try:
        flag1, flag2, flag3, flag4 = True, True, True, True
        defult1, defult2, defult3, defult4 = False, False, False, False

        if 'instanceId' not in request.args.to_dict():  # شروع فرآیند جدید
            flag1 = False
            defult1 = True
        else:
            stateId = request.args.get("stateId")
            if stateId == '230984':  # فرآیند مرحله ی تسهیل‌گر را تمام کرده و اکنون باید تب کارشناس بصیر فعال باشد
                flag1, flag2 = False, False
                defult2 = True
            elif stateId == '230985':  # فرآیند مرحله ی کارشناس بصیر را تمام کرده و اکنون باید تب کارشناس ستاد فعال باشد
                flag1, flag2, flag3 = False, False, False
                defult3 = True
            elif stateId == '230986':  # فرآیند مرحله ی کارشناس ستاد را تمام کرده و اکنون باید تب امور شهرستان فعال باشد
                flag1, flag2, flag3, flag4 = False, False, False, False
                defult4 = True
            elif stateId == '237291':  # فرآیند تمام شده
                flag1, flag2, flag3, flag4 = False, False, False, False
                defult1 = True

        ret = [{
            "type": 'sidebar-infinite',
            "title": 'فرم ها',
            "menuItems": [
                {
                    'title': 'تسهیل‌گر',
                    'disabled': flag1,
                    'indicatorid': '1115',
                    'type': 'statesReport',
                    'method': 'get',
                    'default': defult1,
                    'params': request.args.to_dict()

                },
                {
                    'title': 'کارشناس بصیر',
                    'disabled': flag2,
                    'indicatorid': '1116',
                    'type': 'statesReport',
                    'method': 'get',
                    'default': defult2,
                    'params': request.args.to_dict()
                },
                {
                    'title': 'کارشناس ستاد',
                    'disabled': flag3,
                    'indicatorid': '1117',
                    'type': 'statesReport',
                    'method': 'get',
                    'default': defult3,
                    'params': request.args.to_dict()
                },
                {
                    'title': 'امور شهرستان',
                    'disabled': flag4,
                    'indicatorid': '1122',
                    'type': 'statesReport',
                    'method': 'get',
                    'default': defult4,
                    'params': request.args.to_dict()
                },
            ]
        }]
        return jsonify(ret), 200
    except Exception as ex:
        logger("Error @forms_menu:", ex)
        return jsonify({'title': 'خطا', 'message': 'خطایی رخ داده است'}), 400


# تب تسهیل‌گر
@app.route("/form1")  # indicatorId: 1115
def form1():
    input_params = clear_input_params(request.args)
    current_date = get_current_date()
    user_info = check_permission(request.headers.get("token"))
    # persuitCode = request.args["persuitCode"]

    _flag = False
    instanceId = input_params.get("instanceId", '')
    # sid = request.args.get("sid", '')
    stateId = input_params.get("stateId", '')

    if instanceId != '' and stateId != '':
        _flag = True
        details = get_details_info(int(instanceId), '230984')
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره یک : تسهیل‌گر',
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': details["formDate"]
                },
                {
                    'default_value': details["applicantName"],
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': details["applicantName"],
                    'type': 'inputbox'
                },
                {
                    'default_value': details["reason"],
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'disabled': _flag,
                    'data': get_reason()
                },
                {
                    'default_value': details["reasonDescription"],
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'disabled': _flag,
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'disabled': _flag,
                    'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "بازدید"},
                    'default_value': details["actionType"]
                },
                {
                    'default_value': details["letterNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["applicationName"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'نام نرم افزار',
                    'param': 'applicationName',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["messageNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره ارسال پیام',
                    'param': 'messageNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["messageDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ ارسال پیام',
                    'param': 'messageDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["messageSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه پیام',
                    'param': 'messageSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["contactNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["contactDuration"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["contactDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["contactSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["visitDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ بازدید',
                    'param': 'visitDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["4"]
                },
                {
                    'default_value': details["visitDescription"],
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'visitDescription',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["4"]
                },

            ]
        }]
    else:
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره یک : تسهیل‌گر',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1118',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   # 'persuitCode': persuitCode,
                                   **input_params}
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': request.args.get('reason', ''),
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'disabled': _flag,
                    'data': get_reason()
                },
                {
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'disabled': _flag,
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'disabled': _flag,
                    'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "بازدید"},
                    'default_value': "1"
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'نام نرم افزار',
                    'param': 'applicationName',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره ارسال پیام',
                    'param': 'messageNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('messageDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ ارسال پیام',
                    'param': 'messageDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه پیام',
                    'param': 'messageSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': request.args.get('contactDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': request.args.get('visitDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ بازدید',
                    'param': 'visitDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["4"]
                },
                {
                    'default_value': request.args.get('visitDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'visitDescription',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["4"]
                },

            ]
        }]

    return jsonify(ret), 200


# تب کارشناس بصیر
@app.route("/form2")  # indicatorId: 1116
def form2():
    input_params = clear_input_params(request.args)
    current_date = get_current_date()
    user_info = check_permission(request.headers.get("token"))
    # persuitCode = request.args["persuitCode"]

    instanceId = input_params.get("instanceId", '0')
    # sid = request.args.get("sid", '')
    # stateId = input_params.get("stateId", '')

    details = get_details_info(int(instanceId), '230985')

    # اگر این مرحله برای این اینستنس قبلا تکمیل شده است دیگر اجازه ی تکمیل دوباره داده نشود
    if details is not None:
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره دو : کارشناس بصیر',
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': details["formDate"]
                },
                {
                    'default_value': details["applicantName"],
                    'className': 'col-md-2',
                    'disabled': True,
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': details["reason"],
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'disabled': True,
                    'data': get_reason()
                },

                {
                    'default_value': details["reasonDescription"],
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'disabled': True,
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'disabled': True,
                    'data': {"1": "نامه هشدار", "2": "تماس", "3": "بازدید"},
                    'default_value': details["actionType"]
                },
                {
                    'default_value': details["letterNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': True,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'disabled': True,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': True,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["contactNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': True,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["contactDuration"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': True,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["contactDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'disabled': True,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["contactSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': True,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["visitDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ بازدید',
                    'param': 'visitDate',
                    'value': "",
                    'type': 'date',
                    'disabled': True,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["visitDescription"],
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'visitDescription',
                    'value': "",
                    'type': 'textarea',
                    'disabled': True,
                    'groupId': ["3"]
                },

            ]
        }]
    else:
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره دو : کارشناس بصیر',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1119',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   # 'persuitCode': persuitCode
                                   **input_params}
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'data': get_reason()
                },

                {
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'data': {"1": "نامه هشدار", "2": "تماس", "3": "بازدید"},
                    'default_value': "1"
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["1"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["1"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('contactDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('visitDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ بازدید',
                    'param': 'visitDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["3"]
                },
                {
                    'default_value': request.args.get('visitDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'visitDescription',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["3"]
                },

            ]
        }]

    return jsonify(ret), 200


# تب کارشناس ستاد
@app.route("/form3")  # indicatorId: 1117
def form3():
    input_params = clear_input_params(request.args)
    current_date = get_current_date()
    user_info = check_permission(request.headers.get("token"))
    # persuitCode = request.args["persuitCode"]

    instanceId = input_params.get("instanceId", '0')
    # sid = request.args.get("ssid", '')
    # stateId = input_params.get("stateId", '')

    details = get_details_info(int(instanceId), '230986')

    # اگر این مرحله برای این اینستنس قبلا تکمیل شده است دیگر اجازه ی تکمیل دوباره داده نشود
    if details is not None:
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره سه : کارشناس ستاد',
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': details["formDate"]
                },
                {
                    'default_value': details["applicantName"],
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': details["reason"],
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'disabled': True,
                    'data': get_reason()
                },
                {
                    'default_value': details["reasonDescription"],
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'disabled': True,
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'disabled': True,
                    'data': {"1": "نامه", "2": "اقدام"},
                    'default_value': details["actionType"]
                },
                {
                    'default_value': details["letterNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': True,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'disabled': True,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': True,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["actionDescription"],
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'actionDescription',
                    'value': "",
                    'type': 'textarea',
                    'disabled': True,
                    'groupId': ["2"]
                },
            ]
        }]
    else:
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره سه : کارشناس ستاد',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1120',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   # 'persuitCode': persuitCode
                                   **input_params}
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'data': get_reason()
                },

                {
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'data': {"1": "نامه", "2": "اقدام"},
                    'default_value': "1"
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["1"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('actionDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'actionDescription',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["2"]
                },
            ]
        }]

    return jsonify(ret), 200


# تب امور شهرستان
@app.route("/form4")  # indicatorId: 1122
def form4():
    input_params = clear_input_params(request.args)
    current_date = get_current_date()
    user_info = check_permission(request.headers.get("token"))
    # persuitCode = request.args["persuitCode"]

    _flag = False
    instanceId = input_params.get("instanceId", '')
    # sid = request.args.get("sid", '')
    # stateId = input_params.get("stateId", '')

    details = get_details_info(int(instanceId), '237291')

    # اگر این مرحله برای این اینستنس قبلا تکمیل شده است دیگر اجازه ی تکمیل دوباره داده نشود
    if details is not None:
        _flag = True
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره چهار : امور شهرستان',
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': details["formDate"]
                },
                {
                    'default_value': details["applicantName"],
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': details["applicantName"],
                    'type': 'inputbox'
                },
                {
                    'default_value': details["reason"],
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'disabled': _flag,
                    'data': get_reason()
                },
                {
                    'default_value': details["reasonDescription"],
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'disabled': _flag,
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'disabled': _flag,
                    'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "برنامه رفع مشکل"},
                    'default_value': details["actionType"]
                },
                {
                    'default_value': details["letterNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["letterSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': details["applicationName"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'نام نرم افزار',
                    'param': 'applicationName',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["messageNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره ارسال پیام',
                    'param': 'messageNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["messageDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ ارسال پیام',
                    'param': 'messageDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["messageSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه پیام',
                    'param': 'messageSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': details["contactNo"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["contactDuration"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["contactDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["contactSummary"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': details["programDate"],
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ',
                    'param': 'programDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["4"]
                },
                {
                    'default_value': details["programDescription"],
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'programDescription',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["4"]
                },

            ]
        }]
    else:
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره چهار : امور شهرستان',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1123',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   # 'persuitCode': persuitCode,
                                   **input_params}
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': request.args.get('reason', ''),
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'disabled': _flag,
                    'data': get_reason()
                },
                {
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'disabled': _flag,
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'disabled': _flag,
                    'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "برنامه رفع مشکل"},
                    'default_value': "1"
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["1"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'نام نرم افزار',
                    'param': 'applicationName',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره ارسال پیام',
                    'param': 'messageNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('messageDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ ارسال پیام',
                    'param': 'messageDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه پیام',
                    'param': 'messageSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["2"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': request.args.get('contactDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': '',
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["3"]
                },
                {
                    'default_value': input_params.get('programDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ',
                    'param': 'programDate',
                    'value': "",
                    'type': 'date',
                    'disabled': _flag,
                    'groupId': ["4"]
                },
                {
                    'default_value': request.args.get('programDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'programDescription',
                    'value': "",
                    'type': 'textarea',
                    'disabled': _flag,
                    'groupId': ["4"]
                },

            ]
        }]

    return jsonify(ret), 200


# دکمه ثبت تب تسهیل‌گر
@app.route("/form1Validation")  # 1118
def form1Validation():
    try:
        params = clear_input_params(request.args)
        error = []
        current_date = get_current_date()
        user_info = check_permission(request.headers.get("token"))
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره یک : تسهیل‌گر',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1118',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   **params
                                   }
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': request.args.get('reason', ''),
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'data': get_reason()
                },
                {
                    'default_value': params.get('reasonDescription'),
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "بازدید"},
                    'default_value': params.get('actionType', '')
                },
                {
                    'default_value': params.get('letterNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('letterSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('applicationName', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'نام نرم افزار',
                    'param': 'applicationName',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('messageNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره ارسال پیام',
                    'param': 'messageNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('messageDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ ارسال پیام',
                    'param': 'messageDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('messageSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه پیام',
                    'param': 'messageSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('contactNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["3"]
                },
                {
                    'default_value': params.get('contactDuration', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["3"]
                },
                {
                    'default_value': request.args.get('contactDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["3"]
                },
                {
                    'default_value': params.get('contactSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["3"]
                },
                {
                    'default_value': request.args.get('visitDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ بازدید',
                    'param': 'visitDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["4"]
                },
                {
                    'default_value': params.get('visitDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'visitDescription',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["4"]
                },

            ]
        }]

        try:
            formDate = params.get('formDate', '')
            applicantName = params.get('applicantName', '')
            reason = params.get('reason', '')
            reasonDescription = params.get('reasonDescription', '')
            actionType = params.get('actionType', '')
            letterNo = params.get('letterNo', '')
            letterSummary = params.get('letterSummary', '')
            letterDate = params.get('letterDate', '')
            applicationName = params.get('applicationName', '')
            messageNo = params.get('messageNo', '')
            messageSummary = params.get('messageSummary', '')
            messageDate = params.get('messageDate', '')
            contactNo = params.get('contactNo', '')
            contactDuration = params.get('contactDuration', '')
            contactSummary = params.get('contactSummary', '')
            contactDate = params.get('contactDate', '')
            visitDate = params.get('visitDate', '')
            visitDescription = params.get('visitDescription', '')
            persuitCode = params.get('persuitCode', '')
            creatorId = params.get('creator_id', '')
            unitId, instanceId = get_unit_of_instance(persuitCode)

            details = {'stateId': '230984',
                       'formDate': formDate,
                       'applicantName': applicantName,
                       'reason': reason,
                       'reasonDescription': reasonDescription,
                       'actionType': actionType,
                       'letterNo': letterNo,
                       'letterSummary': letterSummary,
                       'letterDate': letterDate,
                       'applicationName': applicationName,
                       'messageNo': messageNo,
                       'messageSummary': messageSummary,
                       'messageDate': messageDate,
                       'contactNo': contactNo,
                       'contactDuration': contactDuration,
                       'contactSummary': contactSummary,
                       'contactDate': contactDate,
                       'visitDate': visitDate,
                       'visitDescription': visitDescription,
                       'persuitCode': persuitCode}
            details = json.dumps(details)

            reg = '(0|\+98)?([ ]|-|[()]){0,2}9[1|2|3|4]([ ]|-|[()]){0,2}(?:[0-9]([ ]|-|[()]){0,2}){8}'

        except Exception as e:
            raise Exception('Error in getting request.args:', e)

        try:
            if reason is None or reason == 'undefined' or reason == '':
                error.append('عارضه را انتخاب نمایید ')
            if actionType == '1':
                if letterNo == '' or letterNo is None or letterNo == '0':
                    error.append('مقدار فیلد «شماره نامه» نمی‌تواند خالی باشد. ')
                if letterSummary == '' or letterSummary is None or letterSummary == '0':
                    error.append('مقدار فیلد «خلاصه نامه» نمی‌تواند خالی باشد. ')
                if letterDate == '' or letterDate is None or letterDate == '0':
                    error.append('مقدار فیلد «تاریخ نامه» نمی‌تواند خالی باشد. ')
            if actionType == '2':
                if applicationName == '' or applicationName is None or applicationName == '0':
                    error.append('مقدار فیلد «نام نرم افزار» نمی‌تواند خالی باشد. ')
                if messageNo == '' or messageNo is None or messageNo == '0':
                    error.append('مقدار فیلد «شماره ارسال پیام» نمی‌تواند خالی باشد. ')
                if messageSummary == '' or messageSummary is None or messageSummary == '0':
                    error.append('مقدار فیلد «خلاصه پیام» نمی‌تواند خالی باشد. ')
                if messageDate == '' or messageDate is None or messageDate == '0':
                    error.append('مقدار فیلد «تاریخ پیام» نمی‌تواند خالی باشد. ')
            if actionType == '3':
                if contactNo == '' or contactNo is None or contactNo == '0':
                    error.append('مقدار فیلد «شماره تماس» نمی‌تواند خالی باشد. ')
                elif not re.match(reg, contactNo) or len(contactNo) > 11:
                    error.append('قالب صحیح «شماره تماس» باید دارای ۱۱ رقم باشد و با صفر شروع شود. ')
                if contactDuration == '' or contactDuration is None or contactDuration == '0':
                    error.append('مقدار فیلد «مدت زمان» نمی‌تواند خالی باشد. ')
                if contactSummary == '' or contactSummary is None or contactSummary == '0':
                    error.append('مقدار فیلد «خلاصه تماس» نمی‌تواند خالی باشد. ')
                if contactDate == '' or contactDate is None or contactDate == '0':
                    error.append('مقدار فیلد «تاریخ تماس» نمی‌تواند خالی باشد. ')
            if actionType == '4':
                if visitDate == '' or visitDate is None or visitDate == '0':
                    error.append('مقدار فیلد «تاریخ بازدید» نمی‌تواند خالی باشد. ')
                if visitDescription == '' or visitDescription is None or visitDescription == '0':
                    error.append('مقدار فیلد «توضیحات بازدید» نمی‌تواند خالی باشد. ')

        except Exception as e:
            raise Exception('Error in handling wrong fields', e)
        if len(error) > 0:
            ret = [{
                "type": 'form-builder',
                "title": 'فرم شماره یک : تسهیل‌گر',
                "buttons": [
                    {
                        "title": 'ثبت',
                        "onclick": [{
                            'indicatorid': '1118',
                            'method': 'get',
                            'type': 'statesReport',
                            'params': {'creator_id': user_info.get('user_id'),
                                       'creator_username': user_info.get('user_name'),
                                       'creator_fullname': user_info.get('fullname'),
                                       **params}
                        }]
                    }
                ],
                "fields": [
                    {
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'تاریخ تکمیل',
                        'param': 'formDate',
                        'type': 'inputbox',
                        'disabled': True,
                        'value': formDate
                    },
                    {
                        'default_value': params.get('applicantName', ''),
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'نام تکمیل کننده',
                        'param': 'applicantName',
                        'disabled': True,
                        'data': applicantName,
                        'type': 'inputbox'
                    },
                    {
                        'default_value': params.get('reason', ''),
                        'className': 'col-md-2',
                        'groupBox': 1,
                        'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                        'label': 'عارضه',
                        'param': 'reason',
                        'value': "",
                        'type': 'multiselect2',
                        'data': get_reason()
                    },

                    {
                        'groupBox': 1,
                        'label': 'توضیحات',
                        'className': 'col-md-4',
                        'param': 'reasonDescription',
                        'type': 'textarea',
                        'rows': 1,
                        'default_value': params.get('reasonDescription', ''),
                        'data': reasonDescription
                    },
                    {
                        'type': 'groupSelectorRadio',
                        'className': 'col-md-4',
                        'groupBox': 2,
                        'groupTitle': '',
                        'label': 'اقدامات',
                        'param': 'actionType',
                        'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "بازدید"},
                        'default_value': params.get('actionType', '')
                    },
                    {
                        'default_value': params.get('letterNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره نامه',
                        'param': 'letterNo',
                        'value': letterNo,
                        'type': 'inputbox',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ نامه',
                        'param': 'letterDate',
                        'value': letterDate,
                        'type': 'date',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه نامه',
                        'param': 'letterSummary',
                        'value': letterSummary,
                        'type': 'textarea',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('applicationName', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'نام نرم افزار',
                        'param': 'applicationName',
                        'value': applicationName,
                        'type': 'inputbox',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('messageNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره ارسال پیام',
                        'param': 'messageNo',
                        'value': messageNo,
                        'type': 'inputbox',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('messageDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ ارسال پیام',
                        'param': 'messageDate',
                        'value': messageDate,
                        'type': 'date',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('messageSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه پیام',
                        'param': 'messageSummary',
                        'value': messageSummary,
                        'type': 'textarea',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('contactNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره تلفن',
                        'param': 'contactNo',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('contactDuration', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'مدت زمان',
                        'param': 'contactDuration',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('contactDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ تماس',
                        'param': 'contactDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('contactSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه تماس',
                        'param': 'contactSummary',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('visitDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ بازدید',
                        'param': 'visitDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["4"]
                    },
                    {
                        'default_value': params.get('visitDescription', ''),
                        'className': 'col-md-3',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'توضیحات',
                        'param': 'visitDescription',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["4"]
                    },

                ]
            }]
            return jsonify(err_msg_list(error, ret)), 400
        else:
            connection = get_postgresql_connection()
            try:
                date_gregorian = get_current_date_gregorian()
                cursor = connection.cursor()
                query_instance = '''INSERT INTO "BPM".instance(
                            "sourceInstanceid", "processId", "previousInstanceId", "statusType",
                            "changedStatusDate", "lastUpdateTime", "unitId", "processStartDate")
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id '''
                cursor.execute(query_instance,
                               (persuitCode + str(5643), 5643, int(instanceId), 1, date_gregorian,
                                date_gregorian, int(unitId), date_gregorian))
                mRId = cursor.fetchone()[0]

                cursor.execute('''UPDATE "BPM".instance SET "sourceInstanceid"=%s where id=%s ''',
                               (mRId, mRId,))

                query_state = '''INSERT INTO "BPM"."States"(
                    "stateId", "starterUserId", "stateStartDate", "stateEndDate", "previousStateId",
                    "stateRequriementId", "stateSourceId", "departmentId", "instanceId", "receiveTypeId",
                    "steteComment", "statusType", "changedStatusDate", "durationValue", "nextStateId", "isLastState",
                    "isCalculated")
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s ) RETURNING id '''
                cursor.execute(query_state,
                               (230984, creatorId, date_gregorian,
                                date_gregorian,
                                0, 0, '230984' + str(mRId), '', mRId, 0, 'تسهیل‌گر', 1,
                                date_gregorian,
                                0, 0, False, False))
                mRId_state = cursor.fetchone()[0]

                cursor.execute('''UPDATE "BPM"."States" SET "stateSourceId"=%s where id=%s ''',
                               (mRId_state, mRId_state,))

                query_detail = '''INSERT INTO "BPM"."StateInfoDetails"(
                                    "instanceId", "statesId", "stateInfo")
                                    VALUES (%s, %s, %s) RETURNING id '''
                cursor.execute(query_detail,
                               (mRId, mRId_state, details))

                connection.commit()

                request_code = mRId_state
                if request_code is not None:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره یک : تسهیل‌گر',
                        "fields": [
                            {
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'تاریخ تکمیل',
                                'param': 'formDate',
                                'type': 'inputbox',
                                'disabled': True,
                                'value': formDate
                            },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': applicantName,
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'type': 'multiselect2',
                                'disabled': True,
                                'data': get_reason()
                            },

                            {
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'rows': 1,
                                'disabled': True,
                                'default_value': params.get('reasonDescription', ''),
                                'data': reasonDescription
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'disabled': True,
                                'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "بازدید"},
                                'default_value': params.get('actionType', '')
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': letterNo,
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': letterDate,
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': letterSummary,
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('applicationName', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'نام نرم افزار',
                                'param': 'applicationName',
                                'value': applicationName,
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره ارسال پیام',
                                'param': 'messageNo',
                                'value': messageNo,
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ ارسال پیام',
                                'param': 'messageDate',
                                'value': messageDate,
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه پیام',
                                'param': 'messageSummary',
                                'value': messageSummary,
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره تلفن',
                                'param': 'contactNo',
                                'value': "",
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDuration', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'مدت زمان',
                                'param': 'contactDuration',
                                'value': "",
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ تماس',
                                'param': 'contactDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه تماس',
                                'param': 'contactSummary',
                                'value': "",
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('visitDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ بازدید',
                                'param': 'visitDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["4"]
                            },
                            {
                                'default_value': params.get('visitDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'visitDescription',
                                'value': "",
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["4"]
                            },
                        ]
                    }]
                    error = 'اطلاعات پیگیری شما با کد {} با موفقیت ثبت شد.'.format(str(request_code))
                    return jsonify(err_msg2(error, ret)), 400
                else:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره یک : تسهیل‌گر',
                        "buttons": [
                            {
                                "title": 'ثبت',
                                "onclick": [{
                                    'indicatorid': '1118',
                                    'method': 'get',
                                    'type': 'statesReport',
                                    'params': {'creator_id': user_info.get('user_id'),
                                               'creator_username': user_info.get('user_name'),
                                               'creator_fullname': user_info.get('fullname'),
                                               **params}
                                }]
                            }
                        ],
                        "fields": [
                            {
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'تاریخ تکمیل',
                                'param': 'formDate',
                                'type': 'inputbox',
                                'disabled': True,
                                'value': formDate
                            },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': applicantName,
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'type': 'multiselect2',
                                'data': get_reason()
                            },

                            {
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'rows': 1,
                                'default_value': params.get('reasonDescription', ''),
                                'data': reasonDescription
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "بازدید"},
                                'default_value': params.get('actionType', '')
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': letterNo,
                                'type': 'inputbox',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': letterDate,
                                'type': 'date',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': letterSummary,
                                'type': 'textarea',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('applicationName', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'نام نرم افزار',
                                'param': 'applicationName',
                                'value': applicationName,
                                'type': 'inputbox',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره ارسال پیام',
                                'param': 'messageNo',
                                'value': messageNo,
                                'type': 'inputbox',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ ارسال پیام',
                                'param': 'messageDate',
                                'value': messageDate,
                                'type': 'date',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه پیام',
                                'param': 'messageSummary',
                                'value': messageSummary,
                                'type': 'textarea',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره تلفن',
                                'param': 'contactNo',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDuration', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'مدت زمان',
                                'param': 'contactDuration',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ تماس',
                                'param': 'contactDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه تماس',
                                'param': 'contactSummary',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('visitDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ بازدید',
                                'param': 'visitDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["4"]
                            },
                            {
                                'default_value': params.get('visitDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'visitDescription',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["4"]
                            },

                        ]
                    }]
                    error = 'سرویس با مشکل روبرو شده است. ذخیره اطلاعات فرم امکانپذیر نیست!'
                    return jsonify(err_msg(error, ret)), 400

            except Exception as e:
                raise Exception('Error at inserting to tables', e)
            finally:
                if connection is not None:
                    connection.close()

    except Exception as e:
        error = 'در پردازش فرم خطایی رخ داده است!'
        return jsonify(err_msg(error, ret)), 400


# دکمه ثبت تب کارشناس بصیر
@app.route("/form2Validation")  # 1119
def form2Validation():
    try:
        params = clear_input_params(request.args)
        error = []
        current_date = get_current_date()
        user_info = check_permission(request.headers.get("token"))
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره دو : کارشناس بصیر',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1119',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   **params
                                   }
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': params.get('reason', ''),
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'data': get_reason()
                },

                {
                    'default_value': params.get('reasonDescription', ''),
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'data': {"1": "نامه هشدار", "2": "تماس", "3": "بازدید"},
                    'default_value': params.get('actionType', '')
                },
                {
                    'default_value': params.get('letterNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('letterSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('contactNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('contactDuration', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('contactDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('contactSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('visitDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ بازدید',
                    'param': 'visitDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["3"]
                },
                {
                    'default_value': params.get('visitDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'visitDescription',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["3"]
                },

            ]
        }]
        try:
            formDate = params.get('formDate', '')
            applicantName = params.get('applicantName', '')
            reason = params.get('reason', '')
            reasonDescription = params.get('reasonDescription', '')
            actionType = params.get('actionType', '')
            letterNo = params.get('letterNo', '')
            letterSummary = params.get('letterSummary', '')
            letterDate = params.get('letterDate', '')
            contactNo = params.get('contactNo', '')
            contactDuration = params.get('contactDuration', '')
            contactSummary = params.get('contactSummary', '')
            contactDate = params.get('contactDate', '')
            visitDate = params.get('visitDate', '')
            visitDescription = params.get('visitDescription', '')
            persuitCode = params.get('persuitCode', '')
            creatorId = params.get('creator_id', '')
            instanceId = params.get('instanceId', '')

            details = {'stateId': '230985',
                       'formDate': formDate,
                       'applicantName': applicantName,
                       'reason': reason,
                       'reasonDescription': reasonDescription,
                       'actionType': actionType,
                       'letterNo': letterNo,
                       'letterSummary': letterSummary,
                       'letterDate': letterDate,
                       'contactNo': contactNo,
                       'contactDuration': contactDuration,
                       'contactSummary': contactSummary,
                       'contactDate': contactDate,
                       'visitDate': visitDate,
                       'visitDescription': visitDescription,
                       'persuitCode': persuitCode}
            details = json.dumps(details)

            reg = '(0|\+98)?([ ]|-|[()]){0,2}9[1|2|3|4]([ ]|-|[()]){0,2}(?:[0-9]([ ]|-|[()]){0,2}){8}'

        except Exception as e:
            raise Exception('Error in getting request.args:', e)

        try:
            if reason is None or reason == 'undefined' or reason == '':
                error.append('عارضه را انتخاب نمایید ')
            if actionType == '1':
                if letterNo == '' or letterNo is None or letterNo == '0':
                    error.append('مقدار فیلد «شماره نامه» نمی‌تواند خالی باشد. ')
                if letterSummary == '' or letterSummary is None or letterSummary == '0':
                    error.append('مقدار فیلد «خلاصه نامه» نمی‌تواند خالی باشد. ')
                if letterDate == '' or letterDate is None or letterDate == '0':
                    error.append('مقدار فیلد «تاریخ نامه» نمی‌تواند خالی باشد. ')
            if actionType == '2':
                if contactNo == '' or contactNo is None or contactNo == '0':
                    error.append('مقدار فیلد «شماره تماس» نمی‌تواند خالی باشد. ')
                elif not re.match(reg, contactNo) or len(contactNo) > 11:
                    error.append('قالب صحیح «شماره تماس» باید دارای ۱۱ رقم باشد و با صفر شروع شود. ')
                if contactDuration == '' or contactDuration is None or contactDuration == '0':
                    error.append('مقدار فیلد «مدت زمان» نمی‌تواند خالی باشد. ')
                if contactSummary == '' or contactSummary is None or contactSummary == '0':
                    error.append('مقدار فیلد «خلاصه تماس» نمی‌تواند خالی باشد. ')
                if contactDate == '' or contactDate is None or contactDate == '0':
                    error.append('مقدار فیلد «تاریخ تماس» نمی‌تواند خالی باشد. ')
            if actionType == '3':
                if visitDate == '' or visitDate is None or visitDate == '0':
                    error.append('مقدار فیلد «تاریخ بازدید» نمی‌تواند خالی باشد. ')
                if visitDescription == '' or visitDescription is None or visitDescription == '0':
                    error.append('مقدار فیلد «توضیحات بازدید» نمی‌تواند خالی باشد. ')

        except Exception as e:
            raise Exception('Error in handling wrong fields', e)
        if len(error) > 0:
            ret = [{
                "type": 'form-builder',
                "title": 'فرم شماره دو : کارشناس بصیر',
                "buttons": [
                    {
                        "title": 'ثبت',
                        "onclick": [{
                            'indicatorid': '1119',
                            'method': 'get',
                            'type': 'statesReport',
                            'params': {'creator_id': user_info.get('user_id'),
                                       'creator_username': user_info.get('user_name'),
                                       'creator_fullname': user_info.get('fullname'),
                                       **params}
                        }]
                    }
                ],
                "fields": [
                    {
                        'default_value': params.get('formDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'تاریخ تکمیل',
                        'param': 'formDate',
                        'type': 'inputbox',
                        'disabled': True,
                        'value': formDate
                    },
                    {
                        'default_value': params.get('applicantName', ''),
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'نام تکمیل کننده',
                        'param': 'applicantName',
                        'disabled': True,
                        'data': user_info.get('fullname'),
                        'type': 'inputbox'
                    },
                    {
                        'default_value': params.get('reason', ''),
                        'className': 'col-md-2',
                        'groupBox': 1,
                        'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                        'label': 'عارضه',
                        'param': 'reason',
                        'value': "",
                        'type': 'multiselect2',
                        'data': get_reason()
                    },

                    {
                        'default_value': params.get('reasonDescription', ''),
                        'groupBox': 1,
                        'label': 'توضیحات',
                        'className': 'col-md-4',
                        'param': 'reasonDescription',
                        'type': 'textarea',
                        'rows': 1
                    },
                    {
                        'type': 'groupSelectorRadio',
                        'className': 'col-md-4',
                        'groupBox': 2,
                        'groupTitle': '',
                        'label': 'اقدامات',
                        'param': 'actionType',
                        'data': {"1": "نامه هشدار", "2": "تماس", "3": "بازدید"},
                        'default_value': params.get('actionType', ''),
                    },
                    {
                        'default_value': params.get('letterNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره نامه',
                        'param': 'letterNo',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ نامه',
                        'param': 'letterDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه نامه',
                        'param': 'letterSummary',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('contactNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره تلفن',
                        'param': 'contactNo',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('contactDuration', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'مدت زمان',
                        'param': 'contactDuration',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('contactDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ تماس',
                        'param': 'contactDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('contactSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه تماس',
                        'param': 'contactSummary',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('visitDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ بازدید',
                        'param': 'visitDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('visitDescription', ''),
                        'className': 'col-md-3',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'توضیحات',
                        'param': 'visitDescription',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["3"]
                    },

                ]
            }]
            return jsonify(err_msg_list(error, ret)), 400
        else:
            connection = get_postgresql_connection()
            try:
                date_gregorian = get_current_date_gregorian()
                cursor = connection.cursor()
                mRId = int(instanceId)

                query_state = '''INSERT INTO "BPM"."States"(
                    "stateId", "starterUserId", "stateStartDate", "stateEndDate", "previousStateId",
                    "stateRequriementId", "stateSourceId", "departmentId", "instanceId", "receiveTypeId",
                    "steteComment", "statusType", "changedStatusDate", "durationValue", "nextStateId", "isLastState",
                    "isCalculated")
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s ) RETURNING id '''
                cursor.execute(query_state,
                               (230985, creatorId, date_gregorian,
                                date_gregorian,
                                0, 0, '230985' + str(mRId), '', mRId, 0, 'کارشناس بصیر', 1,
                                date_gregorian,
                                0, 0, False, False))
                mRId_state = cursor.fetchone()[0]

                cursor.execute('''UPDATE "BPM"."States" SET "stateSourceId"=%s where id=%s ''',
                               (mRId_state, mRId_state,))

                query_detail = '''INSERT INTO "BPM"."StateInfoDetails"(
                                    "instanceId", "statesId", "stateInfo")
                                    VALUES (%s, %s, %s) RETURNING id '''
                cursor.execute(query_detail,
                               (mRId, mRId_state, details))

                connection.commit()
                request_code = mRId_state
                if request_code is not None:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره دو : کارشناس بصیر',
                        "fields": [
                            {
                                'className': 'col-md-2',
                                'default_value': params.get('formDate', current_date),
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'تاریخ تکمیل',
                                'param': 'formDate',
                                'type': 'inputbox',
                                'disabled': True,
                                'value': formDate
                            },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': user_info.get('fullname'),
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'disabled': True,
                                'type': 'multiselect2',
                                'data': get_reason()
                            },

                            {
                                'default_value': params.get('reasonDescription', ''),
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'disabled': True,
                                'rows': 1
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'disabled': True,
                                'data': {"1": "نامه هشدار", "2": "تماس", "3": "بازدید"},
                                'default_value': params.get('actionType', '')
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': "",
                                'disabled': True,
                                'type': 'inputbox',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': "",
                                'disabled': True,
                                'type': 'textarea',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('contactNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره تلفن',
                                'param': 'contactNo',
                                'value': "",
                                'disabled': True,
                                'type': 'inputbox',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactDuration', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'مدت زمان',
                                'param': 'contactDuration',
                                'value': "",
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ تماس',
                                'param': 'contactDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه تماس',
                                'param': 'contactSummary',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('visitDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ بازدید',
                                'param': 'visitDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('visitDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'visitDescription',
                                'value': "",
                                'disabled': True,
                                'type': 'textarea',
                                'groupId': ["3"]
                            },

                        ]
                    }]
                    error = 'اطلاعات پیگیری شما با کد {} با موفقیت ثبت شد.'.format(str(request_code))
                    return jsonify(err_msg2(error, ret)), 400
                else:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره دو : کارشناس بصیر',
                        "buttons": [
                            {
                                "title": 'ثبت',
                                "onclick": [{
                                    'indicatorid': '1119',
                                    'method': 'get',
                                    'type': 'statesReport',
                                    'params': {'creator_id': user_info.get('user_id'),
                                               'creator_username': user_info.get('user_name'),
                                               'creator_fullname': user_info.get('fullname'),
                                               **params}
                                }]
                            }
                        ],
                        "fields": [
                            {'default_value': params.get('formDate', current_date),
                             'className': 'col-md-2',
                             'groupBox': 0,
                             'groupTitle': '',
                             'label': 'تاریخ تکمیل',
                             'param': 'formDate',
                             'type': 'inputbox',
                             'disabled': True,
                             'value': formDate
                             },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': user_info.get('fullname'),
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'type': 'multiselect2',
                                'data': get_reason()
                            },

                            {
                                'default_value': params.get('reasonDescription', ''),
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'rows': 1
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'data': {"1": "نامه هشدار", "2": "تماس", "3": "بازدید"},
                                'default_value': params.get('actionType', ''),
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('contactNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره تلفن',
                                'param': 'contactNo',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactDuration', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'مدت زمان',
                                'param': 'contactDuration',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ تماس',
                                'param': 'contactDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه تماس',
                                'param': 'contactSummary',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('visitDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ بازدید',
                                'param': 'visitDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('visitDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'visitDescription',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["3"]
                            },

                        ]
                    }]
                    error = 'سرویس با مشکل روبرو شده است. ذخیره اطلاعات فرم امکانپذیر نیست!'
                    return jsonify(err_msg(error, ret))

            except Exception as e:
                raise Exception('Error at inserting to tables', e)
            finally:
                if connection is not None:
                    connection.close()
    except Exception as e:
        error = 'در پردازش فرم خطایی رخ داده است!'
        return jsonify(err_msg(error, ret)), 400


# دکمه ثبت تب کارشناس ستاد
@app.route("/form3Validation")  # 1120
def form3Validation():
    try:
        params = clear_input_params(request.args)
        error = []
        current_date = get_current_date()
        user_info = check_permission(request.headers.get("token"))
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره سه : کارشناس ستاد',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1120',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   **params}
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': params.get('reason', ''),
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'data': get_reason()
                },

                {
                    'default_value': params.get('reasonDescription', ''),
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'data': {"1": "نامه", "2": "اقدام"},
                    'default_value': params.get('actionType', '')
                },
                {
                    'default_value': params.get('letterNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('letterSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('actionDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'actionDescription',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["2"]
                },
            ]
        }]
        try:
            formDate = params.get('formDate', '')
            applicantName = params.get('applicantName', '')
            reason = params.get('reason', '')
            reasonDescription = params.get('reasonDescription', '')
            actionType = params.get('actionType', '')
            letterNo = params.get('letterNo', '')
            letterSummary = params.get('letterSummary', '')
            letterDate = params.get('letterDate', '')
            actionDescription = params.get('actionDescription', '')
            persuitCode = params.get('persuitCode', '')
            creatorId = params.get('creator_id', '')
            instanceId = params.get('instanceId', '')

            details = {'stateId': '230986',
                       'formDate': formDate,
                       'applicantName': applicantName,
                       'reason': reason,
                       'reasonDescription': reasonDescription,
                       'actionType': actionType,
                       'letterNo': letterNo,
                       'letterSummary': letterSummary,
                       'letterDate': letterDate,
                       'actionDescription': actionDescription,
                       'persuitCode': persuitCode}
            details = json.dumps(details)

        except Exception as e:
            raise Exception('Error in getting request.args:', e)

        try:
            if reason is None or reason == 'undefined' or reason == '':
                error.append('عارضه را انتخاب نمایید ')
            if actionType == '1':
                if letterNo == '' or letterNo is None or letterNo == '0':
                    error.append('مقدار فیلد «شماره نامه» نمی‌تواند خالی باشد. ')
                if letterSummary == '' or letterSummary is None or letterSummary == '0':
                    error.append('مقدار فیلد «خلاصه نامه» نمی‌تواند خالی باشد. ')
                if letterDate == '' or letterDate is None or letterDate == '0':
                    error.append('مقدار فیلد «تاریخ نامه» نمی‌تواند خالی باشد. ')
            if actionType == '2':
                if actionDescription == '' or actionDescription is None or actionDescription == '0':
                    error.append('مقدار فیلد «توضیحات اقدام» نمی‌تواند خالی باشد. ')

        except Exception as e:
            raise Exception('Error in handling wrong fields', e)
        if len(error) > 0:
            ret = [{
                "type": 'form-builder',
                "title": 'فرم شماره سه : کارشناس ستاد',
                "buttons": [
                    {
                        "title": 'ثبت',
                        "onclick": [{
                            'indicatorid': '1120',
                            'method': 'get',
                            'type': 'statesReport',
                            'params': {'creator_id': user_info.get('user_id'),
                                       'creator_username': user_info.get('user_name'),
                                       'creator_fullname': user_info.get('fullname'),
                                       **params}
                        }]
                    }
                ],
                "fields": [
                    {
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'تاریخ تکمیل',
                        'param': 'formDate',
                        'type': 'inputbox',
                        'disabled': True,
                        'value': formDate
                    },
                    {
                        'default_value': params.get('applicantName', ''),
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'نام تکمیل کننده',
                        'param': 'applicantName',
                        'disabled': True,
                        'data': user_info.get('fullname'),
                        'type': 'inputbox'
                    },
                    {
                        'default_value': params.get('reason', ''),
                        'className': 'col-md-2',
                        'groupBox': 1,
                        'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                        'label': 'عارضه',
                        'param': 'reason',
                        'value': "",
                        'type': 'multiselect2',
                        'data': get_reason()
                    },

                    {
                        'default_value': params.get('reasonDescription', ''),
                        'groupBox': 1,
                        'label': 'توضیحات',
                        'className': 'col-md-4',
                        'param': 'reasonDescription',
                        'type': 'textarea',
                        'rows': 1
                    },
                    {
                        'type': 'groupSelectorRadio',
                        'className': 'col-md-4',
                        'groupBox': 2,
                        'groupTitle': '',
                        'label': 'اقدامات',
                        'param': 'actionType',
                        'data': {"1": "نامه", "2": "اقدام"},
                        'default_value': params.get('actionType', '')
                    },
                    {
                        'default_value': params.get('letterNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره نامه',
                        'param': 'letterNo',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ نامه',
                        'param': 'letterDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه نامه',
                        'param': 'letterSummary',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('actionDescription', ''),
                        'className': 'col-md-3',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'توضیحات',
                        'param': 'actionDescription',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["2"]
                    },
                ]
            }]
            return jsonify(err_msg_list(error, ret)), 400
        else:
            connection = get_postgresql_connection()
            try:
                date_gregorian = get_current_date_gregorian()
                cursor = connection.cursor()
                # instanceId = pd.read_sql('''select id from "BPM".instance where "sourceInstanceid"=%s ''',
                #                          conn, params=(persuitCode + str(5643),))
                mRId = int(instanceId)

                query_state = '''INSERT INTO "BPM"."States"(
                    "stateId", "starterUserId", "stateStartDate", "stateEndDate", "previousStateId",
                    "stateRequriementId", "stateSourceId", "departmentId", "instanceId", "receiveTypeId",
                    "steteComment", "statusType", "changedStatusDate", "durationValue", "nextStateId", "isLastState",
                    "isCalculated")
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s ) RETURNING id '''
                cursor.execute(query_state,
                               (230986, creatorId, date_gregorian,
                                date_gregorian,
                                0, 0, '230986' + str(mRId), '', mRId, 0, 'کارشناس ستاد', 1,
                                date_gregorian,
                                0, 0, False, False))
                mRId_state = cursor.fetchone()[0]

                cursor.execute('''UPDATE "BPM"."States" SET "stateSourceId"=%s where id=%s ''',
                               (mRId_state, mRId_state,))

                query_detail = '''INSERT INTO "BPM"."StateInfoDetails"(
                                    "instanceId", "statesId", "stateInfo")
                                    VALUES (%s, %s, %s) RETURNING id '''
                cursor.execute(query_detail,
                               (mRId, mRId_state, details))

                connection.commit()

                request_code = mRId_state
                if request_code is not None:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره سه : کارشناس ستاد',
                        "fields": [
                            {
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'تاریخ تکمیل',
                                'param': 'formDate',
                                'type': 'inputbox',
                                'disabled': True,
                                'value': formDate
                            },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': user_info.get('fullname'),
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'disabled': True,
                                'type': 'multiselect2',
                                'data': get_reason()
                            },

                            {
                                'default_value': params.get('reasonDescription', ''),
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'disabled': True,
                                'rows': 1
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'data': {"1": "نامه", "2": "اقدام"},
                                'disabled': True,
                                'default_value': params.get('actionType', '')
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': "",
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': "",
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('actionDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'actionDescription',
                                'value': "",
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                        ]
                    }]
                    error = 'اطلاعات پیگیری شما با کد {} با موفقیت ثبت شد.'.format(str(request_code))
                    return jsonify(err_msg2(error, ret)), 400
                else:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره سه : کارشناس ستاد',
                        "buttons": [
                            {
                                "title": 'ثبت',
                                "onclick": [{
                                    'indicatorid': '1120',
                                    'method': 'get',
                                    'type': 'statesReport',
                                    'params': {'creator_id': user_info.get('user_id'),
                                               'creator_username': user_info.get('user_name'),
                                               'creator_fullname': user_info.get('fullname'),
                                               **params}
                                }]
                            }
                        ],
                        "fields": [
                            {
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'تاریخ تکمیل',
                                'param': 'formDate',
                                'type': 'inputbox',
                                'disabled': True,
                                'value': formDate
                            },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': user_info.get('fullname'),
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'type': 'multiselect2',
                                'data': get_reason()
                            },

                            {
                                'default_value': params.get('reasonDescription', ''),
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'rows': 1
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'data': {"1": "نامه", "2": "اقدام"},
                                'default_value': params.get('actionType', '')
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('actionDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'actionDescription',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["2"]
                            },
                        ]
                    }]
                    error = 'سرویس با مشکل روبرو شده است. ذخیره اطلاعات فرم امکانپذیر نیست!'
                    return jsonify(err_msg(error, ret))

            except Exception as e:
                raise Exception('Error at inserting to tables', e)
            finally:
                if connection is not None:
                    connection.close()

    except Exception as e:
        error = 'در پردازش فرم خطایی رخ داده است!'
        return jsonify(err_msg(error, ret)), 400


# دکمه ثبت تب امور شهرستان
@app.route("/form4Validation")  # 1123
def form4Validation():
    try:
        params = clear_input_params(request.args)
        error = []
        current_date = get_current_date()
        user_info = check_permission(request.headers.get("token"))
        ret = [{
            "type": 'form-builder',
            "title": 'فرم شماره چهار : امور شهرستان',
            "buttons": [
                {
                    "title": 'ثبت',
                    "onclick": [{
                        'indicatorid': '1123',
                        'method': 'get',
                        'type': 'statesReport',
                        'params': {'creator_id': user_info.get('user_id'),
                                   'creator_username': user_info.get('user_name'),
                                   'creator_fullname': user_info.get('fullname'),
                                   **params
                                   }
                    }]
                }
            ],
            "fields": [
                {
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'تاریخ تکمیل',
                    'param': 'formDate',
                    'type': 'inputbox',
                    'disabled': True,
                    'value': current_date
                },
                {
                    'default_value': user_info.get('fullname'),
                    'className': 'col-md-2',
                    'groupBox': 0,
                    'groupTitle': '',
                    'label': 'نام تکمیل کننده',
                    'param': 'applicantName',
                    'disabled': True,
                    'data': user_info.get('fullname'),
                    'type': 'inputbox'
                },
                {
                    'default_value': request.args.get('reason', ''),
                    'className': 'col-md-2',
                    'groupBox': 1,
                    'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                    'label': 'عارضه',
                    'param': 'reason',
                    'value': "",
                    'type': 'multiselect2',
                    'data': get_reason()
                },
                {
                    'default_value': params.get('reasonDescription'),
                    'groupBox': 1,
                    'label': 'توضیحات',
                    'className': 'col-md-4',
                    'param': 'reasonDescription',
                    'type': 'textarea',
                    'rows': 1
                },
                {
                    'type': 'groupSelectorRadio',
                    'className': 'col-md-4',
                    'groupBox': 2,
                    'groupTitle': '',
                    'label': 'اقدامات',
                    'param': 'actionType',
                    'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "برنامه رفع مشکل"},
                    'default_value': params.get('actionType', '')
                },
                {
                    'default_value': params.get('letterNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره نامه',
                    'param': 'letterNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["1"]
                },
                {
                    'default_value': request.args.get('letterDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ نامه',
                    'param': 'letterDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('letterSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه نامه',
                    'param': 'letterSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["1"]
                },
                {
                    'default_value': params.get('applicationName', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'نام نرم افزار',
                    'param': 'applicationName',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('messageNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره ارسال پیام',
                    'param': 'messageNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["2"]
                },
                {
                    'default_value': request.args.get('messageDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ ارسال پیام',
                    'param': 'messageDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('messageSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه پیام',
                    'param': 'messageSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["2"]
                },
                {
                    'default_value': params.get('contactNo', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'شماره تلفن',
                    'param': 'contactNo',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["3"]
                },
                {
                    'default_value': params.get('contactDuration', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'مدت زمان',
                    'param': 'contactDuration',
                    'value': "",
                    'type': 'inputbox',
                    'groupId': ["3"]
                },
                {
                    'default_value': request.args.get('contactDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ تماس',
                    'param': 'contactDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["3"]
                },
                {
                    'default_value': params.get('contactSummary', ''),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'خلاصه تماس',
                    'param': 'contactSummary',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["3"]
                },
                {
                    'default_value': params.get('programDate', current_date),
                    'className': 'col-md-2',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'تاریخ',
                    'param': 'programDate',
                    'value': "",
                    'type': 'date',
                    'groupId': ["4"]
                },
                {
                    'default_value': params.get('programDescription', ''),
                    'className': 'col-md-3',
                    'groupBox': 3,
                    'groupTitle': '',
                    'label': 'توضیحات',
                    'param': 'programDescription',
                    'value': "",
                    'type': 'textarea',
                    'groupId': ["4"]
                },

            ]
        }]

        try:
            formDate = params.get('formDate', '')
            applicantName = params.get('applicantName', '')
            reason = params.get('reason', '')
            reasonDescription = params.get('reasonDescription', '')
            actionType = params.get('actionType', '')
            letterNo = params.get('letterNo', '')
            letterSummary = params.get('letterSummary', '')
            letterDate = params.get('letterDate', '')
            applicationName = params.get('applicationName', '')
            messageNo = params.get('messageNo', '')
            messageSummary = params.get('messageSummary', '')
            messageDate = params.get('messageDate', '')
            contactNo = params.get('contactNo', '')
            contactDuration = params.get('contactDuration', '')
            contactSummary = params.get('contactSummary', '')
            contactDate = params.get('contactDate', '')
            programDate = params.get('programDate', '')
            programDescription = params.get('programDescription', '')
            persuitCode = params.get('persuitCode', '')
            creatorId = params.get('creator_id', '')
            instanceId = params.get('instanceId', '')

            details = {'stateId': '237291',
                       'formDate': formDate,
                       'applicantName': applicantName,
                       'reason': reason,
                       'reasonDescription': reasonDescription,
                       'actionType': actionType,
                       'letterNo': letterNo,
                       'letterSummary': letterSummary,
                       'letterDate': letterDate,
                       'applicationName': applicationName,
                       'messageNo': messageNo,
                       'messageSummary': messageSummary,
                       'messageDate': messageDate,
                       'contactNo': contactNo,
                       'contactDuration': contactDuration,
                       'contactSummary': contactSummary,
                       'contactDate': contactDate,
                       'programDate': programDate,
                       'programDescription': programDescription,
                       'persuitCode': persuitCode}
            details = json.dumps(details)

            reg = '(0|\+98)?([ ]|-|[()]){0,2}9[1|2|3|4]([ ]|-|[()]){0,2}(?:[0-9]([ ]|-|[()]){0,2}){8}'

        except Exception as e:
            raise Exception('Error in getting request.args:', e)

        try:
            if reason is None or reason == 'undefined' or reason == '':
                error.append('عارضه را انتخاب نمایید ')
            if actionType == '1':
                if letterNo == '' or letterNo is None or letterNo == '0':
                    error.append('مقدار فیلد «شماره نامه» نمی‌تواند خالی باشد. ')
                if letterSummary == '' or letterSummary is None or letterSummary == '0':
                    error.append('مقدار فیلد «خلاصه نامه» نمی‌تواند خالی باشد. ')
                if letterDate == '' or letterDate is None or letterDate == '0':
                    error.append('مقدار فیلد «تاریخ نامه» نمی‌تواند خالی باشد. ')
            if actionType == '2':
                if applicationName == '' or applicationName is None or applicationName == '0':
                    error.append('مقدار فیلد «نام نرم افزار» نمی‌تواند خالی باشد. ')
                if messageNo == '' or messageNo is None or messageNo == '0':
                    error.append('مقدار فیلد «شماره ارسال پیام» نمی‌تواند خالی باشد. ')
                if messageSummary == '' or messageSummary is None or messageSummary == '0':
                    error.append('مقدار فیلد «خلاصه پیام» نمی‌تواند خالی باشد. ')
                if messageDate == '' or messageDate is None or messageDate == '0':
                    error.append('مقدار فیلد «تاریخ پیام» نمی‌تواند خالی باشد. ')
            if actionType == '3':
                if contactNo == '' or contactNo is None or contactNo == '0':
                    error.append('مقدار فیلد «شماره تماس» نمی‌تواند خالی باشد. ')
                elif not re.match(reg, contactNo) or len(contactNo) > 11:
                    error.append('قالب صحیح «شماره تماس» باید دارای ۱۱ رقم باشد و با صفر شروع شود. ')
                if contactDuration == '' or contactDuration is None or contactDuration == '0':
                    error.append('مقدار فیلد «مدت زمان» نمی‌تواند خالی باشد. ')
                if contactSummary == '' or contactSummary is None or contactSummary == '0':
                    error.append('مقدار فیلد «خلاصه تماس» نمی‌تواند خالی باشد. ')
                if contactDate == '' or contactDate is None or contactDate == '0':
                    error.append('مقدار فیلد «تاریخ تماس» نمی‌تواند خالی باشد. ')
            if actionType == '4':
                if programDate == '' or programDate is None or programDate == '0':
                    error.append('مقدار فیلد «تاریخ برنامه» نمی‌تواند خالی باشد. ')
                if programDescription == '' or programDescription is None or programDescription == '0':
                    error.append('مقدار فیلد «توضیحات برنامه» نمی‌تواند خالی باشد. ')

        except Exception as e:
            raise Exception('Error in handling wrong fields', e)
        if len(error) > 0:
            ret = [{
                "type": 'form-builder',
                "title": 'فرم شماره چهار : امور شهرستان',
                "buttons": [
                    {
                        "title": 'ثبت',
                        "onclick": [{
                            'indicatorid': '1123',
                            'method': 'get',
                            'type': 'statesReport',
                            'params': {'creator_id': user_info.get('user_id'),
                                       'creator_username': user_info.get('user_name'),
                                       'creator_fullname': user_info.get('fullname'),
                                       **params}
                        }]
                    }
                ],
                "fields": [
                    {
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'تاریخ تکمیل',
                        'param': 'formDate',
                        'type': 'inputbox',
                        'disabled': True,
                        'value': formDate
                    },
                    {
                        'default_value': params.get('applicantName', ''),
                        'className': 'col-md-2',
                        'groupBox': 0,
                        'groupTitle': '',
                        'label': 'نام تکمیل کننده',
                        'param': 'applicantName',
                        'disabled': True,
                        'data': applicantName,
                        'type': 'inputbox'
                    },
                    {
                        'default_value': params.get('reason', ''),
                        'className': 'col-md-2',
                        'groupBox': 1,
                        'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                        'label': 'عارضه',
                        'param': 'reason',
                        'value': "",
                        'type': 'multiselect2',
                        'data': get_reason()
                    },

                    {
                        'groupBox': 1,
                        'label': 'توضیحات',
                        'className': 'col-md-4',
                        'param': 'reasonDescription',
                        'type': 'textarea',
                        'rows': 1,
                        'default_value': params.get('reasonDescription', ''),
                        'data': reasonDescription
                    },
                    {
                        'type': 'groupSelectorRadio',
                        'className': 'col-md-4',
                        'groupBox': 2,
                        'groupTitle': '',
                        'label': 'اقدامات',
                        'param': 'actionType',
                        'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "برنامه رفع مشکل"},
                        'default_value': params.get('actionType', '')
                    },
                    {
                        'default_value': params.get('letterNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره نامه',
                        'param': 'letterNo',
                        'value': letterNo,
                        'type': 'inputbox',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ نامه',
                        'param': 'letterDate',
                        'value': letterDate,
                        'type': 'date',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('letterSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه نامه',
                        'param': 'letterSummary',
                        'value': letterSummary,
                        'type': 'textarea',
                        'groupId': ["1"]
                    },
                    {
                        'default_value': params.get('applicationName', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'نام نرم افزار',
                        'param': 'applicationName',
                        'value': applicationName,
                        'type': 'inputbox',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('messageNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره ارسال پیام',
                        'param': 'messageNo',
                        'value': messageNo,
                        'type': 'inputbox',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('messageDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ ارسال پیام',
                        'param': 'messageDate',
                        'value': messageDate,
                        'type': 'date',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('messageSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه پیام',
                        'param': 'messageSummary',
                        'value': messageSummary,
                        'type': 'textarea',
                        'groupId': ["2"]
                    },
                    {
                        'default_value': params.get('contactNo', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'شماره تلفن',
                        'param': 'contactNo',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('contactDuration', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'مدت زمان',
                        'param': 'contactDuration',
                        'value': "",
                        'type': 'inputbox',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('contactDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ تماس',
                        'param': 'contactDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('contactSummary', ''),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'خلاصه تماس',
                        'param': 'contactSummary',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["3"]
                    },
                    {
                        'default_value': params.get('visitDate', current_date),
                        'className': 'col-md-2',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'تاریخ',
                        'param': 'visitDate',
                        'value': "",
                        'type': 'date',
                        'groupId': ["4"]
                    },
                    {
                        'default_value': params.get('visitDescription', ''),
                        'className': 'col-md-3',
                        'groupBox': 3,
                        'groupTitle': '',
                        'label': 'توضیحات',
                        'param': 'visitDescription',
                        'value': "",
                        'type': 'textarea',
                        'groupId': ["4"]
                    },

                ]
            }]
            return jsonify(err_msg_list(error, ret)), 400
        else:
            connection = get_postgresql_connection()
            try:
                date_gregorian = get_current_date_gregorian()
                cursor = connection.cursor()
                # instanceId = pd.read_sql('''select id from "BPM".instance where "sourceInstanceid"=%s ''',
                #                          conn, params=(persuitCode + str(5643),))
                mRId = int(instanceId)

                cursor.execute('''UPDATE "BPM".instance SET "statusType"=2 where id=%s ''',
                               (mRId,))

                query_state = '''INSERT INTO "BPM"."States"(
                    "stateId", "starterUserId", "stateStartDate", "stateEndDate", "previousStateId",
                    "stateRequriementId", "stateSourceId", "departmentId", "instanceId", "receiveTypeId",
                    "steteComment", "statusType", "changedStatusDate", "durationValue", "nextStateId", "isLastState",
                    "isCalculated")
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s ) RETURNING id '''
                cursor.execute(query_state,
                               (237291, creatorId, date_gregorian,
                                date_gregorian,
                                0, 0, '237291' + str(mRId), '', mRId, 0, 'امور شهرستان', 1,
                                date_gregorian,
                                0, 0, True, False))
                mRId_state = cursor.fetchone()[0]

                cursor.execute('''UPDATE "BPM"."States" SET "stateSourceId"=%s where id=%s ''',
                               (mRId_state, mRId_state,))

                query_detail = '''INSERT INTO "BPM"."StateInfoDetails"(
                                    "instanceId", "statesId", "stateInfo")
                                    VALUES (%s, %s, %s) RETURNING id '''
                cursor.execute(query_detail,
                               (mRId, mRId_state, details))

                connection.commit()

                request_code = mRId_state
                if request_code is not None:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره چهار : امور شهرستان',
                        "fields": [
                            {
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'تاریخ تکمیل',
                                'param': 'formDate',
                                'type': 'inputbox',
                                'disabled': True,
                                'value': formDate
                            },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': applicantName,
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'type': 'multiselect2',
                                'disabled': True,
                                'data': get_reason()
                            },

                            {
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'rows': 1,
                                'disabled': True,
                                'default_value': params.get('reasonDescription', ''),
                                'data': reasonDescription
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'disabled': True,
                                'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "برنامه رفع مشکل"},
                                'default_value': params.get('actionType', '')
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': letterNo,
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': letterDate,
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': letterSummary,
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('applicationName', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'نام نرم افزار',
                                'param': 'applicationName',
                                'value': applicationName,
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره ارسال پیام',
                                'param': 'messageNo',
                                'value': messageNo,
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ ارسال پیام',
                                'param': 'messageDate',
                                'value': messageDate,
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه پیام',
                                'param': 'messageSummary',
                                'value': messageSummary,
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره تلفن',
                                'param': 'contactNo',
                                'value': "",
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDuration', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'مدت زمان',
                                'param': 'contactDuration',
                                'value': "",
                                'type': 'inputbox',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ تماس',
                                'param': 'contactDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه تماس',
                                'param': 'contactSummary',
                                'value': "",
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('programDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ',
                                'param': 'programDate',
                                'value': "",
                                'type': 'date',
                                'disabled': True,
                                'groupId': ["4"]
                            },
                            {
                                'default_value': params.get('programDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'programDescription',
                                'value': "",
                                'type': 'textarea',
                                'disabled': True,
                                'groupId': ["4"]
                            },
                        ]
                    }]
                    error = 'اطلاعات پیگیری شما با کد {} با موفقیت ثبت شد.'.format(str(request_code))
                    return jsonify(err_msg2(error, ret)), 400
                else:
                    ret = [{
                        "type": 'form-builder',
                        "title": 'فرم شماره چهار : امور شهرستان',
                        "buttons": [
                            {
                                "title": 'ثبت',
                                "onclick": [{
                                    'indicatorid': '1123',
                                    'method': 'get',
                                    'type': 'statesReport',
                                    'params': {'creator_id': user_info.get('user_id'),
                                               'creator_username': user_info.get('user_name'),
                                               'creator_fullname': user_info.get('fullname'),
                                               **params}
                                }]
                            }
                        ],
                        "fields": [
                            {
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'تاریخ تکمیل',
                                'param': 'formDate',
                                'type': 'inputbox',
                                'disabled': True,
                                'value': formDate
                            },
                            {
                                'default_value': params.get('applicantName', ''),
                                'className': 'col-md-2',
                                'groupBox': 0,
                                'groupTitle': '',
                                'label': 'نام تکمیل کننده',
                                'param': 'applicantName',
                                'disabled': True,
                                'data': applicantName,
                                'type': 'inputbox'
                            },
                            {
                                'default_value': params.get('reason', ''),
                                'className': 'col-md-2',
                                'groupBox': 1,
                                'groupTitle': '<i class="fa fa-folder-open" aria-hidden="true"></i> عارضه یابی',
                                'label': 'عارضه',
                                'param': 'reason',
                                'value': "",
                                'type': 'multiselect2',
                                'data': get_reason()
                            },

                            {
                                'groupBox': 1,
                                'label': 'توضیحات',
                                'className': 'col-md-4',
                                'param': 'reasonDescription',
                                'type': 'textarea',
                                'rows': 1,
                                'default_value': params.get('reasonDescription', ''),
                                'data': reasonDescription
                            },
                            {
                                'type': 'groupSelectorRadio',
                                'className': 'col-md-4',
                                'groupBox': 2,
                                'groupTitle': '',
                                'label': 'اقدامات',
                                'param': 'actionType',
                                'data': {"1": "نامه", "2": "اطلاع‌رسانی مجازی", "3": "تماس", "4": "برنامه رفع مشکل"},
                                'default_value': params.get('actionType', '')
                            },
                            {
                                'default_value': params.get('letterNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره نامه',
                                'param': 'letterNo',
                                'value': letterNo,
                                'type': 'inputbox',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ نامه',
                                'param': 'letterDate',
                                'value': letterDate,
                                'type': 'date',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('letterSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه نامه',
                                'param': 'letterSummary',
                                'value': letterSummary,
                                'type': 'textarea',
                                'groupId': ["1"]
                            },
                            {
                                'default_value': params.get('applicationName', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'نام نرم افزار',
                                'param': 'applicationName',
                                'value': applicationName,
                                'type': 'inputbox',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره ارسال پیام',
                                'param': 'messageNo',
                                'value': messageNo,
                                'type': 'inputbox',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ ارسال پیام',
                                'param': 'messageDate',
                                'value': messageDate,
                                'type': 'date',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('messageSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه پیام',
                                'param': 'messageSummary',
                                'value': messageSummary,
                                'type': 'textarea',
                                'groupId': ["2"]
                            },
                            {
                                'default_value': params.get('contactNo', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'شماره تلفن',
                                'param': 'contactNo',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDuration', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'مدت زمان',
                                'param': 'contactDuration',
                                'value': "",
                                'type': 'inputbox',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ تماس',
                                'param': 'contactDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('contactSummary', ''),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'خلاصه تماس',
                                'param': 'contactSummary',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["3"]
                            },
                            {
                                'default_value': params.get('programDate', current_date),
                                'className': 'col-md-2',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'تاریخ',
                                'param': 'programDate',
                                'value': "",
                                'type': 'date',
                                'groupId': ["4"]
                            },
                            {
                                'default_value': params.get('programDescription', ''),
                                'className': 'col-md-3',
                                'groupBox': 3,
                                'groupTitle': '',
                                'label': 'توضیحات',
                                'param': 'programDescription',
                                'value': "",
                                'type': 'textarea',
                                'groupId': ["4"]
                            },

                        ]
                    }]
                    error = 'سرویس با مشکل روبرو شده است. ذخیره اطلاعات فرم امکانپذیر نیست!'
                    return jsonify(err_msg(error, ret)), 400

            except Exception as e:
                raise Exception('Error at inserting to tables', e)
            finally:
                if connection is not None:
                    connection.close()

    except Exception as e:
        error = 'در پردازش فرم خطایی رخ داده است!'
        return jsonify(err_msg(error, ret)), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5083, debug=False, use_reloader=False)
    # 5083
