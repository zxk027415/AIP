import pandas as pd
import argparse
import sys
import json
from eapdataset import Dataset
import logging

logger = logging.getLogger(__name__)


def main(sys_args):
    parser = argparse.ArgumentParser(description="demo")
    # 定义输入参数
    parser.add_argument('--predict_output', type=str)
    parser.add_argument('--result_table', type=str)
    parser.add_argument('--label_dataset', type=str)

    # 定义输出参数
    parser.add_argument('--sql_writer', type=str)

    args = parser.parse_args(sys_args)
    result_table = args.result_table
    label_dataset = args.label_dataset

    # 获取上个算子传递的json格式数据
    with open(args.predict_output, "r") as f:
        df_json = json.load(f)

    print(type(df_json))

    logging.info('Save result')
    df = pd.read_json(df_json)
    # tz = df.time_zone.unique()[0]
    # df['time'] = df['time'].apply(lambda x: datetime.fromtimestamp(x),
    #                               pytz.timezone(tz))
    # # to keep the same ts format as original ts
    # df['time'] = df['time'].apply(lambda x: x.strftime("%Y-%m-%d %H:%M:%S"))
    # df.drop('time_zone', axis=1, inplace=True)

    # for hive partition
    df['yyyymmdd'] = pd.to_datetime(df.time).apply(lambda x: x.strftime("%Y%m%d"))
    df['modified_label_id'] = pd.Series()
    df['modified_label_id'] = df['modified_label_id'].fillna('')
    # save result data to dataset by dataset writing
    if 'branch_id' in df.columns:
        no_branch = False
        columns = ['time', 'site_id', 'device_id', 'branch_id', 'predict_label_id', 'modified_label_id', 'yyyymmdd']
    else:
        no_branch = True
        columns = ['time', 'site_id', 'device_id', 'predict_label_id', 'modified_label_id', 'yyyymmdd']
    df = df[columns]
    save_data = df.values.tolist()
    save_dataset = Dataset.get_by_name(label_dataset)
    if no_branch:
        save_num = save_dataset.get_datasource().write(
            save_data, result_table, df.columns.tolist(),
            overwrite=True, keep='modified_label_id',
            join_index=['site_id', 'device_id', 'yyyymmdd'])
    else:
        save_num = save_dataset.get_datasource().write(
            save_data, result_table, df.columns.tolist(),
            overwrite=True, keep='modified_label_id',
            join_index=['site_id', 'branch_id', 'device_id', 'yyyymmdd'])
    logging.info(f"Result saving done for {save_num} rows")

    # 注意字符串的输出定义方式
    # sqls =[]
    # for i, row in df.iterrows():
    #     sql = f"('{row['time']}','{row['site_id']}','{row['device_id']}','{row['branch_id']}','{row['predict_label_id']}',null)"
    #     sqls.append(sql)
    # res = json.dumps([f"insert into {table_name} values " + ','.join(sqls)])
    #
    # Path(args.sql_writer).parent.mkdir(parents=True, exist_ok=True)
    # with open(args.sql_writer, 'w') as f:
    #     f.write('{}'.format(res))


if __name__ == '__main__':
    main(sys.argv[1:])
