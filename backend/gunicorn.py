import multiprocessing

# 工作进程
workers = multiprocessing.cpu_count() * 2 + 1
# 设置守护进程
daemon = True
# 监听内网端口8000
bind = '0.0.0.0:8000'
# 设置为True，开发时用，代码修改会自动重�?
reload = False
# 设置进程文件目录
pidfile = 'logs/gunicorn.pid'
# gunicorn日志文件
accesslog = 'logs/gunicorn_access.log'
errorlog = 'logs/gunicorn_error.log'
# 工作模式
worker_class = 'uvicorn.workers.UvicornWorker'
# 指定每个工作者的线程�?
threads = 2
# 设置最大并发量
worker_connections = 2000
# 错误日志的日志级�?
loglevel = 'info'
