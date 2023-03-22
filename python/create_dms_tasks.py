import csv
import itertools
import json
import subprocess as sp
import os
from configparser import ConfigParser
import sys
import logging
from datetime import datetime
import pandas as pd
import time

def readconfigfile(conf_file):
    src_endpoint_arn, tgt_endpoint_arn, rep_instance_arn, tsk_creation_wait_in_sec, run_flag = '', '', '', '', ''
    try:
        config_read = ConfigParser()
        config_read.read(conf_file)
        run_flag = config_read.get('default','dms_run_flag')
        for i in config_read.sections():
            src_endpoint_arn = config_read.get(env, 'source_endpoint_arn')
            tgt_endpoint_arn = config_read.get(env, 'target_endpoint_arn')
            rep_instance_arn = config_read.get(env, 'replication_instance_arn')
            tsk_creation_wait_in_sec = config_read.getint(env, 'task_creation_wait_in_sec')
    except Exception:
        raise KeyError
    return src_endpoint_arn, tgt_endpoint_arn, rep_instance_arn, tsk_creation_wait_in_sec, run_flag


def readinputdatafile(filepath):
    rows = []
    data = open(filepath, 'r', encoding='utf-8')
    reader = csv.reader(data)
    next(reader)
    for row in reader:
        rows.append(row)
    return rows

def fetchdmstaskdetails(filedata):
    RepTskIdentifier, ReplicationTaskArn, tablename, status = [], [], [], []
    return_code = None
    f = ''
    try:
        create_cmd = 'aws dms describe-replication-tasks --output json >> {}/tasks.json'.format(output_filepath)
        run_cmd = sp.Popen(create_cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)
        run_cmd.wait()
        res = run_cmd.communicate()
        return_code = run_cmd.returncode
        if return_code == 0:
            for line in res[0].decode(encoding='utf-8').split('\n'):
                logger.info(line)
            f = open(output_filepath + '/tasks.json')
            data = json.load(f)
            for rows in filedata:
                table_name = rows[1]
                for i in data['ReplicationTasks']:
                    if i["ReplicationTaskIdentifier"] == (table_name.replace("_","-") + '-' + env):
                        ReplicationTaskArn.append(i["ReplicationTaskArn"])
                        tablename.append(table_name)
                        RepTskIdentifier.append(i["ReplicationTaskIdentifier"])
                        status.append(i["Status"])
        elif return_code != 0:
            logger.info("DMS tasks details fetch command failed with return code: {}".format(return_code))
            for line in res[1].decode(encoding='utf-8').split('\n'):
                logger.info(line)
        else:
            logger.info("Fetching DMS tasks details is not completed. Return code: {}".format(return_code))
    except Exception as e:
        logger.error("An exception was thrown while fetching DMS tasks details!!", exc_info=True)
        print("An exception was thrown while fetching DMS tasks details!!. Check log file for more details!!")
    finally:
        f.close()
        try:
            os.remove(output_filepath + '/tasks.json')
        except OSError as e:
            logger.info("Error while deleting JSON file: %s - %s." % (e.filename, e.strerror))
    return RepTskIdentifier, ReplicationTaskArn, tablename, return_code, status

def createDMStask(data, source_endpoint_arn, target_endpoint_arn, replication_instance_arn, task_creation_wait_in_sec, tabname):
    create_flag = []
    for rows in data:
        table_name = rows[1]
        if table_name and table_name not in tabname:
            table_mapping = table_mapping_path + '/' + env + '/' + table_name
            table_setting = table_setting_path + '/' + env + '/' + table_name
            create_cmd = 'aws dms create-replication-task \
                        --replication-task-identifier ' + table_name.replace("_","-") + '-' + env + ' \
                        --source-endpoint-arn ' + source_endpoint_arn + ' \
                        --target-endpoint-arn ' + target_endpoint_arn + ' \
                        --replication-instance-arn ' + replication_instance_arn + ' \
                        --migration-type full-load-and-cdc \
                        --table-mappings file://' + table_mapping + '.json \
                        --replication-task-settings file://' + table_setting + '.json '
            try:
                run_cmd = sp.Popen(create_cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)
                run_cmd.wait(timeout=task_creation_wait_in_sec)
                res = run_cmd.communicate()
                return_code = run_cmd.returncode
                create_flag.append(return_code)
                if return_code == 0:
                    logger.info("DMS task created Successfully for table: {}".format(table_name))
                elif return_code != 0:
                    logger.info("DMS task creation Failed for table: {}".format(table_name))
                    for line in res[1].decode(encoding='utf-8').split('\n'):
                        logger.info(line)
                else:
                    logger.info("DMS task not created, return code for table: {0} is {1}".format(table_name, return_code))
            except Exception as e:
                logger.error("An exception was thrown while creating DMS task!!", exc_info=True)
        elif table_name in tabname:
            logger.info("DMS task already created for table: {}".format(table_name))
            create_flag.append(1)
        else:
            logger.info("Please enter correct entry in CSV file for Tablename.! Either blank entry or wrong input is provided!")
            create_flag.append(1)
    return create_flag



def runDMStask(replication_task_arn, table_name):
    run_flag = []
    try:
        for (rep_tsk_arn,tab_nm) in itertools.zip_longest(replication_task_arn, table_name):
            create_cmd = 'aws dms start-replication-task \
            --replication-task-arn ' + rep_tsk_arn + ' \
            --start-replication-task-type start-replication'
            run_cmd = sp.run(create_cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
            return_code = run_cmd.returncode
            run_flag.append(return_code)
            if return_code == 0:
                logger.info("DMS task execution started Successfully for Table: {0} with Return_Code: {1}".format(tab_nm, return_code))
            elif return_code != 0:
                logger.info("DMS task execution failed for Table: {0} with Return_Code: {1}".format(tab_nm, return_code))
                logger.info(run_cmd.stderr)
            else:
                logger.info("DMS tasks execution is not triggered for Table: {0} with Return_Code: {1}".format(tab_nm, return_code))
    except Exception as e:
        logger.error("An exception was thrown while running DMS tasks!!", exc_info=True)
        run_flag.append(False)
    return run_flag


def outputresult(rep_tsk_identifier, replication_task_arn, table_name, stat, output_filepath):
    df = pd.DataFrame(([r, t, rep, s] for (r, t, rep, s) in itertools.zip_longest(rep_tsk_identifier, table_name, replication_task_arn, stat))
                      , columns=['ReplicationTaskIdentifier', 'TableName', 'ReplicationTaskArn', 'Status'])
    df.to_csv(output_filepath+'/dms-tasks-status.csv', index=False)

def main():
    print("Script Execution Started!")
    try:
        src_ep_arn, tgt_ep_arn, rep_ins_arn, tsk_creation_wt_in_sec, flag = readconfigfile(conf_file_path)
    except KeyError:
        logger.error("An Exception is thrown while reading the Config File!", exc_info=True)
        raise SystemExit("Error Occurred while reading the Config File. Exiting from program execution. Check Log file.!!")
    try:
        file_data = readinputdatafile(input_filepath)
    except Exception:
        logger.error("An Exception is thrown while reading Input File!", exc_info=True)
        raise SystemExit("Error Occurred while reading the Input File. Exiting from program execution. Check Log file.!!")
        
    replic_tsk_idnt, replication_task_arn, table_name, returncode, st = fetchdmstaskdetails(file_data)
    if returncode == 0:
        create_task_flag = createDMStask(file_data, src_ep_arn, tgt_ep_arn, rep_ins_arn, tsk_creation_wt_in_sec, table_name)
        if 0 in create_task_flag and len(set(create_task_flag)) == 1:
            print("DMS task is Created for all tables!")
        else:
            print("DMS Task Creation encounter an Exception OR Error for one or more tables OR table DMS task is already created OR Blank Entry in Input csv File! Check logs for more details!")
    time.sleep(60)
    rep_tsk_idnt, rep_tsk_arn, tabnm, rtcode, stat = fetchdmstaskdetails(file_data)
    if rtcode == 0 and flag == 'True':
        run_task_flag = runDMStask(rep_tsk_arn, tabnm)
        if 0 in run_task_flag and len(set(run_task_flag)) == 1:
            print("DMS tasks is triggered successfully for all tables!")
        else:
            print("DMS Task Execution encounter an Exception OR Error. DMS task is not triggered for one or more tables.! Check logs for more details!")
    time.sleep(30)
    rep_tsk_identifier, replication_task_arn, table_name, retcode, status = fetchdmstaskdetails(file_data)
    outputresult(rep_tsk_identifier, replication_task_arn, table_name, status, output_filepath)
    print("Script Execution Completed! Check logs and Output Excel for more details!")


if __name__ == '__main__':
    env = ''
    if len(sys.argv) == 2:
        filename = sys.argv[0]
        env = sys.argv[1]
    else:
        raise SystemExit("Please pass correct argument list while calling the script! Enter correct parameter value for environment which is either 'preview', 'prodcopy' or 'prod'!")
    dir_name = os.path.normpath(os.getcwd())
    conf_file_path = [os.path.normpath(os.path.join(dir_name, "dms", "config_files", "dms.config").replace('python', ''))]
    table_mapping_path = os.path.normpath(os.path.join(dir_name, "dms", "config_files", "table_mapping").replace('python', ''))
    table_setting_path = os.path.normpath(os.path.join(dir_name, "dms", "config_files", "table_setting").replace('python', ''))
    input_filepath = os.path.normpath(os.path.join(dir_name, "data", "input", "dms-table-load.csv").replace('python', ''))
    output_filepath = os.path.normpath(os.path.join(dir_name, "data", "output").replace('python', ''))
    if not os.path.exists(output_filepath):
        os.mkdir(output_filepath)
    logpath = os.path.normpath(os.path.join(dir_name, "logs").replace('python', ''))
    if not os.path.exists(logpath):
        os.mkdir(logpath)
    logging.basicConfig(filename=datetime.now().strftime(logpath + "/dms.log"), format='%(asctime)s %(message)s', filemode='w')
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)

main()
