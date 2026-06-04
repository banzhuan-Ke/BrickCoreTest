import * as echarts from 'echarts'

// 亮色主题配置
const lightTheme = {
    chart1: ['#107dec', '#1ab43a', '#ef0d25', '#f4b806', '#676666', "#8a2be2"],
    chart2: ['#1ab43a', '#ef0d25', '#f4b806', '#676666', "#8a2be2", '#107dec'],
    bg: '#ffffff',
    text: '#080a0b',
    axisLine: '#262727',
    splitLine: '#262727'
}

// 清新 Pro 图表配色
const proTheme = {
    chart1: ['#4b6fff', '#20c997', '#ff5b4f', '#ffae42', '#7b8498', '#7c5cff'],
    chart2: ['#20c997', '#ff5b4f', '#ffae42', '#7b8498', '#7c5cff', '#4b6fff'],
    bg: 'rgba(255,255,255,.92)',
    text: '#1f2533',
    axisLine: '#d7def0',
    splitLine: '#edf1f8'
}

// 暗黑主题配置
const darkTheme = {
    chart1: ['#4a90e2', '#32cd32', '#ff4500', '#ffd700', '#a9a9a9', "#9370db"],
    chart2: ['#32cd32', '#ff4500', '#ffd700', '#a9a9a9', "#9370db", '#4a90e2'],
    bg: '#080a0b',
    text: '#ffffff',
    axisLine: '#666666',
    splitLine: '#444444'
}
// 主题获取方法
const getTheme = (isDark) => {
    if (typeof document !== 'undefined' && document.documentElement.classList.contains('theme-pro')) {
        return proTheme
    }
    return isDark ? darkTheme : lightTheme
}

export default {
    // 获取图表1的option配置
    getChart1Option(data, dataLabel, isDark) {
        const theme = getTheme(isDark)
        let barLengths = []
        data.forEach(() => {
            barLengths.push(data[0])
        })
        return {
            backgroundColor: theme.bg,
            grid: {
                top: '3%',
                left: '20%',
                bottom: '3%',
                backgroundColor: theme.bg
            },
            xAxis: { show: false },
            yAxis: [{
                show: true,
                data: dataLabel,
                inverse: true,
                axisLine: { show: false },
                splitLine: { show: false },
                axisTick: { show: false },
                axisLabel: {
                    color: theme.text,
                    fontWeight: 'bold',
                    fontSize: 14
                }
            }, {
                show: false,
                inverse: true,
                data: data,
                axisLabel: {
                    fontSize: 12,
                    color: theme.text,
                },
                axisTick: { show: false },
                axisLine: { show: false }
            }],
            series: [{
                type: 'bar',
                yAxisIndex: 0,
                data: data,
                barCategoryGap: 50,
                barWidth: 12,
                itemStyle: {
                    borderRadius: 6,
                    borderColor: theme.bg,
                    color: ({ dataIndex }) => theme.chart1[dataIndex % theme.chart1.length],
                    borderWidth: 1
                }
            }, {
                type: 'bar',
                yAxisIndex: 1,
                barCategoryGap: 50,
                data: barLengths,
                barWidth: 16,
                itemStyle: {
                    color: 'none',
                    borderWidth: 2,
                    borderRadius: 6
                },
                label: {
                    show: true,
                    position: 'right',
                    formatter: '{b}条',
                    color: theme.text,
                    fontWeight: 'bold',
                    fontSize: 14
                }
            }]
        }
    },

    // 获取图表2的option配置
    getChart2Option(datas, isDark) {
        const theme = getTheme(isDark)
        return {
            backgroundColor: theme.bg,
            color: theme.chart2,
            tooltip: {
                trigger: 'item',
                formatter: '{d}%【{c}条用例】',
                backgroundColor: theme.bg,
                borderColor: theme.text,
                textStyle: {
                    color: theme.text,
                    fontSize: '16',
                    fontWeight: 'bold'
                }
            },
            legend: {
                orient: 'vertical',
                right: 10,
                bottom: 10,
                textStyle: {
                    color: theme.text,
                    fontWeight: 'bold'
                }
            },
            series: [{
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                label: {
                    show: false,
                    position: 'center'
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: '20',
                        fontWeight: 'bold',
                        color: theme.text,
                    }
                },
                labelLine: {
                    show: false,
                    color: theme.text
                },
                data: datas
            }]
        }
    },

    // 用例信息图表（横向柱状图）
    chart1(ele, data, dataLabel, isDark) {
        /*
        ele:显示图表的元素
        data:包含数据的数组 [100，80，13，7]
        dataLabel:包含数据的名称的数组 ['用例总数', '通过用例', '失败用例', '错误用例', '跳过用例', '未运行用例']
        */
        const theme = getTheme(isDark)
        //1.初始化chart01
        const chart1 = echarts.init(ele)
        let barLengths = []
        data.forEach((item) => {
            barLengths.push(data[0])
        })
        //2.配置数据
        // 柱状图颜色数组
        const option = {
            backgroundColor: theme.bg,
            //图标位置
            grid: {
                top: '3%',
                left: '20%',
                bottom: '3%',
                backgroundColor: theme.bg
            },
            xAxis: {
                show: false
            },
            yAxis: [{
                show: true,
                data: dataLabel,
                inverse: true,
                axisLine: {
                    show: false
                },
                splitLine: {
                    show: false
                },
                axisTick: {
                    show: false
                },
                axisLabel: {
                    color: theme.text,
                    fontWeight: 'bold',
                    fontSize: 14
                }
            },
                {
                    show: false,
                    inverse: true,
                    data: data,
                    axisLabel: {
                        fontSize: 12,
                        color: theme.text,
                    },
                    axisTick: {
                        show: false
                    },
                    axisLine: {
                        show: false
                    }
                }
            ],
            series: [{
                type: 'bar',
                yAxisIndex: 0,
                data: data,
                barCategoryGap: 50,
                barWidth: 12,
                itemStyle: {
                    borderRadius: 6,
                    borderColor: theme.bg,
                    color: ({dataIndex}) => theme.chart1[dataIndex % theme.chart1.length],
                    borderWidth: 1
                }
            },
                {
                    type: 'bar',
                    yAxisIndex: 1,
                    barCategoryGap: 50,
                    data: barLengths,
                    barWidth: 16,
                    itemStyle: {
                        color: 'none',
                        borderWidth: 2,
                        borderRadius: 6
                    },
                    label: {
                        show: true,
                        position: 'right',
                        formatter: '{b}条',
                        color: theme.text,
                        fontWeight: 'bold',
                        fontSize: 14
                    }
                }
            ]
        }
        // 渲染图表
        chart1.setOption(option)
        return chart1
    },

    // 用例图表（饼图）
    chart2(ele, datas, isDark) {
        /*
        ele：展示图表的元素
        datas: 通过率数据：格式如下
            [{
                value: 80,
                name: '处理完'
            }, {
                value: 30,
                name: '处理中'
            }, {
                value: 10,
                name: '未处理'
            }, {
                value: 1,
                name: '无效的'
            }]
        */
        const theme = getTheme(isDark)
        //1.初始化chart2
        const chart2 = echarts.init(ele)
        //2 图表样式配置
        // 饼状图颜色
        const option = {
            backgroundColor: theme.bg,
            color: theme.chart2,
            tooltip: {
                trigger: 'item',
                formatter: '{d}%【{c}条用例】',
                backgroundColor: theme.bg,
                borderColor: theme.text,
                textStyle: {
                    color: theme.text,
                    fontSize: '16',
                    fontWeight: 'bold'
                }
            },
            legend: {
                orient: 'vertical',
                right: 10,
                bottom: 10,
                textStyle: {
                    color: theme.text,
                    fontWeight: 'bold'
                }
            },
            series: [{
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                label: {
                    show: false,
                    position: 'center'
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: '20',
                        fontWeight: 'bold',
                        color: theme.text,
                    }
                },
                labelLine: {
                    show: false,
                    color: theme.text
                },
                data: datas
            }]
        }
        //3、渲染图表
        chart2.setOption(option)
        return chart2
    },
}