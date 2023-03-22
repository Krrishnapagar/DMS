import os
import psycopg2
from psycopg2 import pool
from pandas_profiling import ProfileReport
#from pandas_profiling import ydata_profiling
import psycopg2.pool
from configparser import ConfigParser
import pandas as pd
import pandas_profiling
import csv #import to use the csv module
import sys
import logging
from datetime import datetime

def readconfigfile(conf_file):
    
    try:
        config_read = ConfigParser()
        config_read.read(conf_file)
        logger.info(config_read.sections)
        
        postgreSQL_pool = psycopg2.pool.SimpleConnectionPool(1, 20, host = config_read.get(env, 'database_host'),

                                                                    port = config_read.getint(env, 'database_port'),

                                                                    dbname = config_read.get(env, 'database_name'),

                                                                    user = config_read.get(env, 'username'),

                                                                    password = config_read.get(env, 'password'))
        print(env)
    except Exception:
        raise KeyError
    return postgreSQL_pool


def readfile_giveoutput(filepath,ps_connection,ps_cursor,output_filepath):
    data = open(filepath, 'r', encoding='utf-8')
    tables = csv.reader(data)
    next(tables)
    for item in tables:
        table= item[1]
        if env=='prodcopy':
            output = os.path.normpath(os.path.join(output_filepath,"{}_prodcopy.html").format(table))
            
        elif env=='preview':
            output= os.path.normpath(os.path.join(output_filepath,'{}_preview.html').format(table))
        elif env=='prod':
            output = os.path.normpath(os.path.join(output_filepath,'{}_prod.html').format(table))          
        sql= 'SELECT * FROM ' + table
        ps_cursor.execute(sql)
        records = ps_cursor.fetchall()
        df= pd.read_sql(sql, ps_connection)
        pd.set_option('display.expand_frame_repr', False)
        profile = ProfileReport(df, minimal=True,explorative=False)
        if env=='prodcopy':
            profile.to_file(output)
        elif env=="preview":
            profile.to_file(output)
        elif env=="prod":
            profile.to_file(output)
            
        
    

def main():
    logger.info("Data Profiling Report Generation Started\n")
    try:
        postgreSQL_pool = readconfigfile(conf_file_path)
        print(output_filepath)
    except KeyError:
        logger.error("An Exception is thrown while reading the Config File!\n", exc_info=True)
        raise SystemExit("Exiting the program execution. Check Log file.!!")
    logger.info("Connection pool created successfully")
    try:
        ps_connection = postgreSQL_pool.getconn()
        ps_cursor = ps_connection.cursor()
        try:
            readfile_giveoutput(input_filepath,ps_connection,ps_cursor,output_filepath)
        except Exception:
            logger.error("An Exception is thrown while reading Input File!\n", exc_info=True)
            raise SystemExit("Exiting the program execution. Check Log file.!!\n")
        ps_cursor.close()
        postgreSQL_pool.putconn(ps_connection)
        logger.info("Put away a PostgreSQL connection\n")
    except Exception:
        logger.error("Unable connecting to connection pool\n", exc_info=True)
    if postgreSQL_pool:
            postgreSQL_pool.closeall
            logger.info("PostgreSQL connection pool is closed\n")


if __name__ == '__main__':
    env = ''
    if len(sys.argv) == 2:
        filename = sys.argv[0]
        env = sys.argv[1]
    else:
        raise SystemExit("Please pass correct argument list while calling the script!!! Enter correct parameter value for environment which is either 'preview', 'prodcopy' or 'prod'!!!")
    dir_name = os.path.normpath(os.getcwd())
    conf_file_path = [os.path.normpath(os.path.join(dir_name, "dms", "config_files", "dms.config").replace('python', ''))]
    input_filepath = os.path.normpath(os.path.join(dir_name, "data", "input", "profiling-tables.csv").replace('python', ''))
    #output_filepath = os.path.normpath(os.path.join(dir_name,'output'))
    output_file= os.path.normpath(os.path.join(dir_name, "data", "output").replace('python', ''))
    if  not os.path.exists(output_file) : 
        os.mkdir(output_file)
    if env=='prodcopy':
        
        output_filepath = os.path.normpath(os.path.join(dir_name, "data", "output","prodcopy").replace('python', ''))
        if  not os.path.exists(output_filepath) :
           os.mkdir(output_filepath)
    elif env=='preview':
        
        output_filepath = os.path.normpath(os.path.join(dir_name, "data", "output","preview").replace('python', '')) 
        if  not os.path.exists(output_filepath) : 
            os.mkdir(output_filepath)
        
    elif env=='prod':  
        output_filepath = os.path.normpath(os.path.join(dir_name, "data", "output","prod").replace('python', ''))
        if  not os.path.exists(output_filepath):
           os.mkdir(output_filepath)
    log_filepath = os.path.normpath(os.path.join(dir_name,"data","output","log").replace('python', ''))
    
    if  not os.path.exists(log_filepath) :
        os.mkdir(log_filepath) 
    
    logging.basicConfig(filename=datetime.now().strftime(log_filepath + "/log_profiling_automation_%Y-%m-%d_%H-%M-%S.log"), format='%(asctime)s %(message)s', filemode='w')
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)

# Calling Main Function
main()