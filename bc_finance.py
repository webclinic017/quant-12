# -*- coding: utf-8 -*-
"""
Utilities in finance calculation

:author: Beichen Chen
"""
import pandas as pd
import numpy as np
import datetime
import math
from quant import bc_util as util
from quant import bc_technical_analysis as ta_util


#----------------------------- Rate and Risk -----------------------------------#
# risk_premium = mean(excess_return)
# risk = std(excess_return)
def cal_HPR(data, start, end, dim='Close', dividends=0):
  """
  Calculate Holding-Period-Rate

  :param data: original OHLCV data
  :param start: start date
  :param end: end date
  :param dim: price dim to calculate
  :param dividends: divndends to add
  :returns: HPR
  :raises: none
  """
  data = data[start:end][dim].tolist()
  HPR = (data[-1] - data[0]) / data[0]
  
  return HPR


def cal_EAR(data, start, end, dim='Close', dividends=0):
  """
  Calculate Effective-Annual-Rate

  :param data: original OHLCV data
  :param start: start date
  :param end: end date
  :param dim: price dim to calculate
  :param dividends: divndends to add
  :returns: EAR
  :raises: none
  """
  # calculate HPR in specific period
  HPR = cal_HPR(data, start, end, dim, dividends) + 1
  
  # convert the period to year
  start_date = util.time_2_string(data[start:end].index.min())
  end_date = util.time_2_string(data[start:end].index.max())
  period_in_year = util.num_days_between(start_date, end_date) / 365.0
  
  # calculate EAR
  EAR = pow(HPR, 1/period_in_year) - 1
  
  return EAR


def cal_APR(data, start, end, dim='Close', dividends=0):
  """
  Calculate Annual-Percentile-Rate

  :param data: original OHLCV data
  :param start: start date
  :param end: end date
  :param dim: price dim to calculate
  :param dividends: divndends to add
  :returns: APR
  :raises: none
  """
  # calculate the HPR in specific period
  HPR = cal_HPR(data, start, end, dim, dividends)
  
  # convert the period to year
  start_date = util.time_2_string(data[start:end].index.min())
  end_date = util.time_2_string(data[start:end].index.max())
  period_in_year = util.num_days_between(start_date, end_date) / 365.0
  
  # calculate APR
  APR = HPR / period_in_year
  
  return APR


def cal_CCR(data, start, end, dim='Close', dividends=0):
  """
  Calculate Continuous-Compouding-Rate

  :param data: original OHLCV data
  :param start: start date
  :param end: end date
  :param dim: price dim to calculate
  :param dividends: divndends to add
  :returns: CCR
  :raises: none
  """
  EAR = cal_EAR(data, start, end, dim, dividends)
  CCR = math.log((1+EAR), math.e)
  
  return CCR


def cal_risk_premium(expected_rate, risk_free_rate):
  """
  Calculate Risk-Premium

  :param expected_rate: expected rate
  :param risk_free_rate: the pre-defined risk-free-rate
  :returns: risk premium
  :raises: none
  """
  RP = expected_rate - risk_free_rate
  
  return RP


def cal_excess_raturn(expected_rate, real_rate):
  """
  Calculate Excess-Return

  :param expected_rate: expected rate
  :param real_rate: real rate
  :returns: ER
  :raises: none
  """
  ER = real_rate - expected_rate
  
  return ER


def cal_period_rate_risk(data, dim='Close', by='month'):
  """
  Calculate rate and risk in a specfic period

  :param data: original OHLCV data
  :param dim: price dim to calculate
  :param by: by which period: year/month/week
  :returns: periodical return and risk
  :raises: none
  """
  # calculate the change rate by day
  data = ta_util.cal_change_rate(df=data, target_col=dim, periods=1)

  # get start/end date, construct period list
  start_date = data.index.min().date()
  end_date = data.index.max().date()
  periods = []

  # by year
  if by == 'year':
    for year in range(start_date.year, end_date.year+1):
      p = '%(year)s' % dict(year=year)
      periods.append((p, p))
      
  # by month      
  elif by == 'month':
    for year in range(start_date.year, end_date.year+1):
      for month in range(1, 13):
        if year >= end_date.year and month > end_date.month:
          break
        p = '%(year)s-%(month)02d' % dict(year=year, month=month)
        periods.append((p, p))

  # by week
  elif by == 'week':
    week_start = start_date
    while week_start < end_date:
      week_end = week_start + datetime.timedelta(days=(6 - week_start.weekday()))
      periods.append((week_start, week_end))
      week_start = week_end + datetime.timedelta(days=1)
  else:
    print('Invalid period')
  
  # calculate the risk/return for the period
  period_rate = {
      'period': [],
      'start': [],
      'end': [],
      'HPR': [],
      'EAR': [],
      'APR': [],
      'CCR': [],
      'daily_rate_mean': [],
      'daily_rate_std': []
  } 
  for p_pair in periods:
    tmp_data = data[p_pair[0]:p_pair[1]]
    if len(tmp_data) <= 1:
      continue
    else:
      period_rate['period'].append(p_pair[0])
      period_rate['start'].append(p_pair[0])
      period_rate['end'].append(p_pair[1])
      period_rate['HPR'].append(cal_HPR(data=tmp_data, start=None, end=None, dim='Close'))
      period_rate['EAR'].append(cal_EAR(data=tmp_data, start=None, end=None, dim='Close'))
      period_rate['APR'].append(cal_APR(data=tmp_data, start=None, end=None, dim='Close'))
      period_rate['CCR'].append(cal_CCR(data=tmp_data, start=None, end=None, dim='Close'))
      period_rate['daily_rate_mean'].append(tmp_data.rate.mean())
      period_rate['daily_rate_std'].append(tmp_data.rate.std())
  
  period_rate = pd.DataFrame(period_rate)
  period_rate = util.df_2_timeseries(df=period_rate, time_col='period')
  
  return period_rate


def cal_sharp_ratio(data, ear, rfr=0.04, rate_dim='rate', days_a_year=252):
  sharp_ratio = (ear - rfr) / (data[rate_dim].std() * days_a_year**0.5)
  return sharp_ratio

def cal_max_drawndown(data, value_dim='value'):

  data = data.copy()
  data['drawndown'] = 0

  for index, row in data.iterrows():
    current_max = data[:index][value_dim].max()
    current = data.loc[index, value_dim]
    data.loc[index, 'drawndown'] = (current_max - current) / current_max

  max_drawndown = data['drawndown'].max()

  return max_drawndown

