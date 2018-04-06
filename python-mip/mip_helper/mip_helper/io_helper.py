#!/usr/bin/env python3

import logging
import sqlalchemy
import pandas
import os
import datetime
import re
import json
import numpy as np
from sqlalchemy.exc import ProgrammingError

from .models import JobResult


# *********************************************************************************************************************
# Initialization
# *********************************************************************************************************************

# Configure logging
logging.basicConfig(level=logging.INFO)

# Init sessionmaker
Session = sqlalchemy.orm.sessionmaker()


# *********************************************************************************************************************
# Public functions
# *********************************************************************************************************************

def fetch_data():
    """
    Get all the needed  algorithm inputs (data, algorithm parameters, etc).
    The inputs format is described in the README file.
    """
    engine = sqlalchemy.create_engine(_get_input_db_url())

    data = dict()
    var = _get_var()
    covars = _get_covars()
    metadata = _get_metadata()

    try:
        df = pandas.read_sql_query(_get_query(), engine)
        raw_data = df.to_dict('list')
        data['dependent'] = [_format_variable(var, raw_data, metadata)] if var else []
        data['independent'] = [_format_variable(v, raw_data, metadata) for v in covars]
    except ProgrammingError as ex:
        logging.warning("A problem occurred while querying the database, "
                        "please ensure all the variables are available in the database: " + str(ex))

    parameters = _get_parameters()

    inputs = {'data': data, 'parameters': parameters}

    return inputs


def fetch_parameters():
    """Get parameters from env variables."""
    return _get_parameters()


def save_results(pfa, error, shape):
    """
    Store algorithm results in the output DB. Update results if it already exists.
    :param pfa: PFA formatted results
    :param error: Error message (if any)
    :param shape: Result shape. For example: pfa_json.
    """
    engine = sqlalchemy.create_engine(_get_output_db_url())

    sql = sqlalchemy.text("INSERT INTO job_result VALUES(:job_id, :node, :timestamp, :data, :error, :shape, :function)")
    engine.execute(sql,
                   job_id=_get_job_id(),
                   node=_get_node(),
                   timestamp=datetime.datetime.utcnow(),
                   data=pfa,
                   error=error,
                   shape=shape,
                   function=_get_function())


def get_results(job_id=None, node=None):
    """
    Return job result as a dictionary if exists. Return None if it does not exist.
    :param job_id: Job ID
    """
    assert isinstance(job_id, str)
    engine = sqlalchemy.create_engine(_get_output_db_url())
    Session.configure(bind=engine)

    session = Session()
    job_id = job_id or _get_job_id()
    node = node or _get_node()
    job_result = session.query(JobResult).filter_by(job_id=job_id, node=node).first()
    session.close()

    return job_result


def get_param(params_list, param_name, type, default_value):
    """Extract param and convert it into proper type."""
    for p in params_list:
        if p["name"] == param_name:
            try:
                return type(p["value"])
            except ValueError:
                logging.info('%s cannot be cast as %s' % (p['value'], str(type)))
    logging.info("Using default value of parameter %s: %s" % (param_name, default_value))
    return type(default_value)


def get_boolean_param(params_list, param_name, default_value):
    """Extract boolean parameter from input['parameters'].
    :param params_list: input['parameters']
    :param param_name:
    :param default_value:
    """
    for p in params_list:
        if p["name"] == param_name:
            try:
                return p["value"].lower() in ("yes", "true", "t", "1")
            except ValueError:
                logging.warning("%s cannot be cast to boolean !")
    logging.info("Using default value: %s for %s" % (default_value, param_name))
    return default_value


# *********************************************************************************************************************
# Private functions
# *********************************************************************************************************************

def _format_variable(var_code, raw_data, vars_meta):
    var_type = _get_type(var_code, vars_meta)
    series = _get_series(raw_data, var_code)
    var = {'name': var_code, 'type': var_type, 'series': series}
    var_meta = vars_meta[var_code]
    if var['type']['name'] in ('real', 'integer'):
        for stat in ['mean', 'std', 'min', 'max']:
            if stat in var_meta:
                var[stat] = float(var_meta[stat])
    var['label'] = var_meta.get('label', var_code)
    return var


def _get_series(raw_data, var_code):
    series = raw_data[var_code]
    return [None if np.isreal(s) and s is not None and np.isnan(s) else s for s in series]


def _get_parameters():
    param_prefix = "MODEL_PARAM_"
    research_pattern = param_prefix + ".*"
    parameters = []
    for env_var in os.environ:
        if re.fullmatch(research_pattern, env_var):
            parameters.append({'name': env_var.split(param_prefix)[1], 'value': os.environ[env_var]})
    return parameters


def _get_type(var_code, vars_meta):
    type_info = dict()
    try:
        var_meta = vars_meta[var_code]
        type_info['name'] = var_meta.get('type', 'unknown')
        if type_info['name'] in ['polynominal', 'binominal']:
            type_info['enumeration'] = [e['code'] for e in var_meta['enumerations']]
            # NOTE: enumeration could be a dictionary {'code': <code>, 'label': <label>}, this is only for
            # backward compatibility
            type_info['enumeration_labels'] = [e['label'] for e in var_meta['enumerations']]
    except KeyError:
        logging.warning("Cannot read meta-data for variable %s !", var_code)
        type_info['name'] = 'unknown'
    return type_info


def _get_input_db_url():
    try:
        dbapi = os.environ['IN_DBAPI_DRIVER']
    except KeyError:
        logging.warning("Cannot read input DBAPI from environment variable IN_DBAPI_DRIVER")
        dbapi = "postgresql"

    try:
        host = os.environ['IN_HOST']
    except KeyError:
        logging.warning("Cannot read host for input database from environment variable IN_HOST")
        raise

    try:
        port = os.environ['IN_PORT']
    except KeyError:
        logging.warning("Cannot read port for input database from environment variable IN_PORT")
        raise

    try:
        database = os.environ['IN_DATABASE']
    except KeyError:
        logging.warning("Cannot read name of input database from environment variable IN_DATABASE")
        raise

    try:
        user = os.environ['IN_USER']
    except KeyError:
        logging.warning("Cannot read input database user from environment variable IN_USER")
        raise

    try:
        passwd = os.environ['IN_PASSWORD']
    except KeyError:
        logging.warning("Cannot read input database password from environment variable IN_PASSWORD")
        raise

    input_db_url = dbapi + "://" + user + ":" + passwd + "@" + host + ":" + port + "/" + database

    return input_db_url


def _get_output_db_url():
    try:
        dbapi = os.environ['OUT_DBAPI_DRIVER']
    except KeyError:
        logging.warning("Cannot read output DBAPI from environment variable OUT_DBAPI_DRIVER")
        dbapi = "postgresql"

    try:
        host = os.environ['OUT_HOST']
    except KeyError:
        logging.warning("Cannot read host for output database from environment variable OUT_HOST")
        raise

    try:
        port = os.environ['OUT_PORT']
    except KeyError:
        logging.warning("Cannot read port for output database from environment variable OUT_PORT")
        raise

    try:
        database = os.environ['OUT_DATABASE']
    except KeyError:
        logging.warning("Cannot read name of output database from environment variable OUT_DATABASE")
        raise

    try:
        user = os.environ['OUT_USER']
    except KeyError:
        logging.warning("Cannot read output database user from environment variable OUT_USER")
        raise

    try:
        passwd = os.environ['OUT_PASSWORD']
    except KeyError:
        logging.warning("Cannot read output database password from environment variable OUT_PASSWORD")
        raise

    output_db_url = dbapi + "://" + user + ":" + passwd + "@" + host + ":" + port + "/" + database

    return output_db_url


def _get_metadata():
    try:
        return json.loads(os.environ['PARAM_meta'])
    except KeyError:
        logging.warning("Cannot read metadata from environment variable PARAM_meta")


def _get_query():
    try:
        return os.environ['PARAM_query']
    except KeyError:
        logging.warning("Cannot read SQL query from environment variable PARAM_query")


def _get_var():
    try:
        return os.environ['PARAM_variables']
    except KeyError:
        logging.warning("Cannot read dependent variables from environment variable PARAM_variables")


def _get_covars():
    try:
        covars = os.environ['PARAM_covariables']
    except KeyError:
        covars = ""
    try:
        gvars = os.environ['PARAM_grouping']
    except KeyError:
        gvars = ""
    return list(filter(None, re.split(', |,', covars))) + list(filter(None, re.split(', |,', gvars)))


def _get_job_id():
    try:
        return os.environ['JOB_ID']
    except KeyError:
        logging.warning("Cannot read job ID from environment variable JOB_ID")


def _get_node():
    try:
        return os.environ['NODE']
    except KeyError:
        logging.warning("Cannot read node from environment variable NODE")


def _get_function():
    try:
        return os.environ['FUNCTION']
    except KeyError:
        logging.warning("Cannot read function from environment variable FUNCTION")
