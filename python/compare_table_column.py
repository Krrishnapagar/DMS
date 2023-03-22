import csv
import sys
import psycopg2
import pandas as pd
import numpy as np
import os
import logging
from datetime import datetime
from configparser import ConfigParser


def getdbconnection(env):
    username, password, database_host, database_port, database_name = '', '', '', '', ''
    config_read = ConfigParser()
    config_read.read(conf_file_path)
    try:
        for i in config_read.sections():
            username = config_read.get(env, 'username')
            password = config_read.get(env, 'password')
            database_host = config_read.get(env, 'database_host')
            database_port = config_read.getint(env, 'database_port')
            database_name = config_read.get(env, 'database_name')
    except Exception:
        raise KeyError
    connection = psycopg2.connect(database=database_name, user=username, password=password, host=database_host, port=database_port)
    if connection.closed == 0:
        cursor = connection.cursor()
    else:
        raise psycopg2.Error
    return connection, cursor


def readinputfile(input_file):
    rows = []
    data = open(input_file, 'r', encoding='utf-8')
    reader = csv.reader(data)
    for row in reader:
        rows.append(row)
    return rows


def inputdf(table_name, db1_cursor, db2_cursor):
    query = "select table_name, column_name, data_type from information_schema.columns where table_name = '{}';".format(table_name)
    db1_df = pd.DataFrame()
    db2_df = pd.DataFrame()
    try:
        if table_name:
            db1_cursor.execute(query)
            db1_record = db1_cursor.fetchall()
            db1_df = pd.DataFrame(db1_record, columns=['TableName', 'ColumnName', 'DataType']).fillna('')
            db2_cursor.execute(query)
            db2_record = db2_cursor.fetchall()
            db2_df = pd.DataFrame(db2_record, columns=['TableName', 'ColumnName', 'DataType']).fillna('')
        else:
            logger.info("Table Name is not present in the input excel in first column of Sheet 1")
    except Exception as e:
        logger.error("An Exception is thrown while fetching data from tables and creating input dataframe!", exc_info=True)
    return db1_df, db2_df, table_name


def compare(db1DF, db2DF, tablename):
    new_data = []
    merge_df = db1DF.merge(db2DF, indicator=True, how='outer')
    data_diff = merge_df.loc[lambda x: x['_merge'] != 'both']
    if data_diff.empty and not db1DF.empty and not db2DF.empty:
        logger.info("{} - Meta Data is Matching".format(tablename))
    elif data_diff.empty and db1DF.empty and db2DF.empty:
        logger.info("{} - Table is not present in Database".format(tablename))
        final_db1_df = pd.DataFrame({"Environment": [database1.upper()], "TableName": [tablename], "ColumnName": [''], "DataType": [''], "Result": ['Table is not present']})
        final_db2_df = pd.DataFrame({"Environment": [database2.upper()], "TableName": [tablename], "ColumnName": [''], "DataType": [''], "Result": ['Table is not present']})
        join_df = [final_db1_df, final_db2_df]
        df = pd.concat(join_df, ignore_index=True)
        for index, rows in df.iterrows():
            my_list = [rows.Environment, rows.TableName, rows.ColumnName, rows.DataType, rows.Result]
            new_data.append(my_list)
    else:
        logger.info("{} - Meta Data is not Matching".format(tablename))
        final_db1_df = data_diff.loc[lambda x: x['_merge'] == 'left_only']
        if not final_db1_df.empty:
            final_db1_df.insert(0, 'Environment', database1.upper())
            final_db1_df = final_db1_df.drop(['_merge'], axis=1)
            final_db1_df.insert(4, 'Result', 'Meta Data is not Matching. Addition, Removal or Mismatch in Column Name')
        else:
            final_db1_df = final_db1_df.assign(Environment=[database1.upper()], TableName=[tablename], ColumnName=[''], DataType=[''], Result=['Remaining Columns in {0} are matching with {1}'.format(database1.upper(), database2.upper())])
        final_db2_df = data_diff.loc[lambda x: x['_merge'] == 'right_only']
        if not final_db2_df.empty:
            final_db2_df.insert(0, 'Environment', database2.upper())
            final_db2_df = final_db2_df.drop(['_merge'], axis=1)
            final_db2_df.insert(4, 'Result', 'Meta Data is not Matching. Addition, Removal or Mismatch in Column Name')
        else:
            final_db2_df = final_db2_df.assign(Environment=[database2.upper()], TableName=[tablename], ColumnName=[''], DataType=[''], Result=['Remaining Columns in {1} are matching with {0}'.format(database1.upper(), database2.upper())])
        join_df = [final_db1_df, final_db2_df]
        df = pd.concat(join_df, ignore_index=True)
        try:
            for index, rows in df.iterrows():
                my_list = [rows.Environment, rows.TableName, rows.ColumnName, rows.DataType, rows.Result]
                new_data.append(my_list)
        except Exception as e:
            logger.error("An Exception is thrown while creating output data list!", exc_info=True)
    return new_data


def outputresult(data):
    outdf = pd.DataFrame(data, columns=['Environment', 'TableName', 'ColumnName', 'DataType', 'Result'])
    outdf.to_csv(outputfile + '/staging-schema-compare.csv', index=False)


def main():
    logger.info("Script Execution Started!!")
    try:
        db1_conn, db1_cursor = getdbconnection(database1)
        db2_conn, db2_cursor = getdbconnection(database2)
    except KeyError:
        logger.error("An Exception is thrown while reading the Config File!", exc_info=True)
        raise SystemExit("Error Occurred while reading the Config File. Exiting the program execution. Check Log file")
    except psycopg2.Error:
        logger.error("An Exception is thrown while Connecting to DB!", exc_info=True)
        raise SystemExit("Error Occurred while Connecting to DB. Exiting the program execution. Check Log file")
    try:
        rows = readinputfile(filepath)
    except Exception:
        logger.error("An Exception is thrown while reading Input File!", exc_info=True)
        raise SystemExit("Error Occurred while reading the Input File. Exiting the program execution. Check Log file")
    new_data = []
    for line in rows[1:]:
        table_name = line[0]
        db1_df, db2_df, tablename = inputdf(table_name, db1_cursor, db2_cursor)
        data = compare(db1_df, db2_df, tablename)
        new_data.extend(data)
    try:
        outputresult(new_data)
    except Exception as e:
        logger.error("An Exception is thrown while writing data to Output Result File!", exc_info=True)
        print("An Exception is thrown while writing data to Output Result File!")
    finally:
        if db1_conn.closed == 0:
            db1_conn.close()
        if db2_conn.closed == 0:
            db2_conn.close()
    logger.info("Script Execution Completed!")
    print("Script Execution Completed!! Check Output file for more details!!")


if __name__ == '__main__':
    if len(sys.argv) == 3:
        database1 = sys.argv[1]
        database2 = sys.argv[2]
    else:
        raise SystemExit("Please pass correct Database name for Schema Comparison!!")
    dir_name = os.path.normpath(os.getcwd())
    conf_file_path = [os.path.normpath(os.path.join(dir_name, "dms", "config_files", "dms.config").replace('python', ''))]
    filepath = os.path.normpath(os.path.join(dir_name, "data", "input", "staging-table-list.csv").replace('python', ''))
    outputfile = os.path.normpath(os.path.join(dir_name, "data", "output").replace('python', ''))
    if not os.path.exists(outputfile):
        os.mkdir(outputfile)
    logpath = os.path.normpath(os.path.join(dir_name, "logs").replace('python', ''))
    if not os.path.exists(logpath):
        os.mkdir(logpath)
    logging.basicConfig(filename=datetime.now().strftime(logpath + "/schema-compare.log"), format='%(asctime)s %(message)s', filemode='w')
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)

# Calling Main Function
main()
