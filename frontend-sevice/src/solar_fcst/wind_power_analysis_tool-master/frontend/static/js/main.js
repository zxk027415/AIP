// 风速优化预测数据分析工具 - 主JavaScript文件

// 全局变量
let currentStationId = null;
let currentDataId = null;
let currentFeatureId = null;
let currentModelId = null;
let availableSources = [];
let selectedSources = [];

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('风速优化预测数据分析工具已加载');
    
    // 初始化
    initializeApp();
});

// ============================================================================
// 初始化和事件监听器设置
// ============================================================================

function initializeApp() {
    // 加载场站列表
    loadStations();
    
    // 设置事件监听器
    setupEventListeners();
    
    // 设置默认日期范围（最近15天）
    setDefaultDateRange();
    
    // 设置默认预测日期范围
    setDefaultPredictDateRange();
}

function setupEventListeners() {
    // 场站选择变更
    document.getElementById('stationSelect').addEventListener('change', onStationChange);
    
    // 应用设置按钮
    document.getElementById('applySettings').addEventListener('click', onApplySettings);
    
    // 刷新按钮
    document.getElementById('refreshData').addEventListener('click', onRefreshData);
    
    // 特征工程相关
    document.getElementById('selectAllFeatures').addEventListener('click', selectAllFeatureGroups);
    document.getElementById('deselectAllFeatures').addEventListener('click', deselectAllFeatureGroups);
    document.getElementById('generateFeatures').addEventListener('click', onGenerateFeatures);
    
    // 模型训练相关
    document.getElementById('trainModel').addEventListener('click', onTrainModel);
    document.querySelectorAll('input[name="modelType"]').forEach(radio => {
        radio.addEventListener('change', onModelTypeChange);
    });
    
    // 导出功能
    document.getElementById('exportDataChart').addEventListener('click', () => exportChart('timeseriesChart'));
    
    // 标签页切换事件
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', onTabChange);
    });
}

function setDefaultDateRange() {
    // 设置默认日期范围为最近一个月
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 1);
    
    // 格式化为YYYY-MM-DD格式（避免时区问题）
    const endDateStr = formatDateToYYYYMMDD(endDate);
    const startDateStr = formatDateToYYYYMMDD(startDate);
    
    // 设置日期输入框的值
    document.getElementById('endDate').value = endDateStr;
    document.getElementById('startDate').value = startDateStr;
    
    console.log(`设置默认日期范围: ${startDateStr} 到 ${endDateStr}`);
}

// 辅助函数：格式化日期为YYYY-MM-DD
function formatDateToYYYYMMDD(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// 快捷日期范围设置
function setQuickDateRange(days) {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);
    
    const endDateStr = formatDateToYYYYMMDD(endDate);
    const startDateStr = formatDateToYYYYMMDD(startDate);
    
    document.getElementById('endDate').value = endDateStr;
    document.getElementById('startDate').value = startDateStr;
    
    console.log(`快捷设置日期范围: 最近${days}天 (${startDateStr} 到 ${endDateStr})`);
}

// ============================================================================
// 场站管理和数据加载 (任务 9.1)
// ============================================================================

async function loadStations() {
    try {
        const response = await fetch('/api/stations');
        const data = await handleApiResponse(response);
        
        const stationSelect = document.getElementById('stationSelect');
        stationSelect.innerHTML = '<option value="">请选择场站</option>';
        
        data.stations.forEach(station => {
            const option = document.createElement('option');
            option.value = station;
            option.textContent = station;
            stationSelect.appendChild(option);
        });
        
        console.log(`已加载 ${data.stations.length} 个场站`);
    } catch (error) {
        handleError('加载场站列表失败', error);
    }
}

async function onStationChange(event) {
    currentStationId = event.target.value;
    
    if (!currentStationId) {
        return;
    }
    
    console.log(`场站切换到: ${currentStationId}`);
    
    // 重置状态
    currentDataId = null;
    currentFeatureId = null;
    currentModelId = null;
    availableSources = [];
    selectedSources = [];
    
    // 清空气象源选择
    updateSourcesMenu([]);
    
    // 设置默认日期范围为最近一个月
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 1);
    
    // 格式化为YYYY-MM-DD格式
    const endDateStr = formatDateToYYYYMMDD(endDate);
    const startDateStr = formatDateToYYYYMMDD(startDate);
    
    document.getElementById('endDate').value = endDateStr;
    document.getElementById('startDate').value = startDateStr;
    
    console.log(`设置默认日期范围: ${startDateStr} 到 ${endDateStr}`);
    
    // 自动加载数据
    await loadStationData();
}

async function onApplySettings() {
    if (!currentStationId) {
        showError('请先选择场站');
        return;
    }
    
    await loadStationData();
}

async function onRefreshData() {
    if (!currentStationId) {
        showError('请先选择场站');
        return;
    }
    
    await loadStationData();
}

async function loadStationData() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const resolution = document.getElementById('resolutionSelect').value;
    
    if (!startDate || !endDate) {
        showError('请选择日期范围');
        return;
    }
    
    showLoading(true);
    
    try {
        // 加载数据
        const loadResponse = await fetch('/api/data/load', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                station_id: currentStationId,
                resolution: resolution,
                start_date: startDate,
                end_date: endDate
            })
        });
        
        const loadData = await handleApiResponse(loadResponse);
        currentDataId = loadData.data_id;
        availableSources = loadData.info.sources || [];  // 修复：从 info.sources 获取
        
        console.log(`数据已加载，data_id: ${currentDataId}`);
        console.log(`数据时间范围: ${startDate} 到 ${endDate}`);
        console.log(`可用气象源: ${availableSources.join(', ')}`);
        
        // 检查是否有被删除的列
        if (loadData.info.removed_columns && loadData.info.removed_columns.length > 0) {
            console.warn('检测到完全缺失的气象要素，已自动删除:');
            loadData.info.removed_columns.forEach(item => {
                console.warn(`  - ${item.source}: ${item.features.join(', ')}`);
            });
            
            // 显示提示信息
            showWarning(`数据质量提示：检测到 ${loadData.info.removed_columns.length} 个气象源的部分要素完全缺失，已自动删除。详情请查看控制台。`);
        }
        
        // 保存用户之前选择的气象源
        const previouslySelectedSources = [...selectedSources];
        
        // 更新气象源选择菜单
        updateSourcesMenu(availableSources);
        
        // 如果之前有选择的气象源，保留用户的选择
        if (previouslySelectedSources.length > 0) {
            // 只保留仍然可用的气象源
            selectedSources = previouslySelectedSources.filter(source => 
                availableSources.includes(source)
            );
            console.log(`保留用户之前的气象源选择: ${selectedSources.join(', ')}`);
        }
        
        // 如果没有之前的选择，或者之前选择的气象源都不可用了，使用默认选择
        if (selectedSources.length === 0) {
            const defaultSources = ['EC_10D', 'ENS_AVG'];
            selectedSources = availableSources.filter(source => 
                defaultSources.some(defaultSrc => source.includes(defaultSrc))
            );
            
            // 如果没有找到默认气象源，则选择所有
            if (selectedSources.length === 0) {
                selectedSources = [...availableSources];
            }
            console.log(`使用默认气象源选择: ${selectedSources.join(', ')}`);
        }
        
        // 更新UI中的复选框状态
        updateSourceCheckboxes();
        
        // 更新标签显示
        updateSourceTagsDisplay();
        
        // 显示时间序列数据
        console.log('初始加载时间序列数据，使用气象源:', selectedSources);
        await displayTimeseriesData();
        
        // 如果当前在统计分析标签页，自动刷新统计分析
        const activeTab = document.querySelector('.nav-link.active');
        if (activeTab && activeTab.getAttribute('data-bs-target') === '#analysis-panel') {
            console.log('检测到当前在统计分析标签页，自动刷新统计分析...');
            await displayStatisticalAnalysis();
        }
        
    } catch (error) {
        handleError('加载数据失败', error);
    } finally {
        showLoading(false);
    }
}

function updateSourcesMenu(sources) {
    const menu = document.getElementById('sourcesMenu');
    menu.innerHTML = '';
    
    if (sources.length === 0) {
        menu.innerHTML = '<li><small class="text-muted px-2">加载数据后可选择</small></li>';
        return;
    }
    
    sources.forEach(source => {
        const li = document.createElement('li');
        li.className = 'px-2 py-1';
        
        const div = document.createElement('div');
        div.className = 'form-check';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'form-check-input source-checkbox';
        checkbox.value = source;
        checkbox.id = `source_${source}`;
        // 默认选中EC_10D和ENS_AVG相关的气象源
        const defaultSources = ['EC_10D', 'ENS_AVG'];
        checkbox.checked = defaultSources.some(defaultSrc => source.includes(defaultSrc));
        // 添加点击事件，立即更新标签显示
        checkbox.addEventListener('change', onSourceCheckboxChange);
        
        const label = document.createElement('label');
        label.className = 'form-check-label';
        label.htmlFor = `source_${source}`;
        label.textContent = source;
        label.style.cursor = 'pointer';
        
        div.appendChild(checkbox);
        div.appendChild(label);
        li.appendChild(div);
        menu.appendChild(li);
    });
    
    // 添加全选/取消全选按钮
    const divider = document.createElement('li');
    divider.innerHTML = '<hr class="dropdown-divider my-2">';
    menu.appendChild(divider);
    
    const buttonsLi = document.createElement('li');
    buttonsLi.className = 'px-2 py-1 d-flex gap-2';
    buttonsLi.innerHTML = `
        <button class="btn btn-sm btn-outline-primary flex-fill" onclick="selectAllSources()">全选</button>
        <button class="btn btn-sm btn-outline-secondary flex-fill" onclick="deselectAllSources()">取消全选</button>
    `;
    menu.appendChild(buttonsLi);
}

// 复选框变更时更新标签显示（不重新加载数据）
function onSourceCheckboxChange() {
    selectedSources = Array.from(document.querySelectorAll('.source-checkbox:checked'))
        .map(cb => cb.value);
    
    console.log(`气象源选择变更 - 已选择: ${selectedSources.join(', ')}`);
    
    // 只更新标签显示，不重新加载数据
    updateSourceTagsDisplay();
}

// 应用气象源选择（重新加载数据）
function onSourceSelectionChange() {
    selectedSources = Array.from(document.querySelectorAll('.source-checkbox:checked'))
        .map(cb => cb.value);
    
    console.log(`应用气象源选择 - 已选择: ${selectedSources.join(', ')}`);
    
    // 更新标签显示
    updateSourceTagsDisplay();
    
    // 重新显示时间序列数据
    if (currentDataId) {
        console.log('重新加载时间序列数据...');
        displayTimeseriesData();
        
        // 如果当前在统计分析标签页，也刷新统计分析
        const activeTab = document.querySelector('.nav-link.active');
        if (activeTab && activeTab.getAttribute('data-bs-target') === '#analysis-panel') {
            console.log('刷新统计分析数据...');
            displayStatisticalAnalysis();
        }
    } else {
        console.warn('未加载数据，无法更新图表');
    }
}

// 更新气象源标签显示
function updateSourceTagsDisplay() {
    const container = document.getElementById('selectedSourcesTags');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (selectedSources.length === 0) {
        const placeholder = document.createElement('small');
        placeholder.className = 'text-muted px-2';
        placeholder.textContent = '请选择气象源';
        container.appendChild(placeholder);
        return;
    }
    
    // 为每个选中的气象源创建标签
    selectedSources.forEach(source => {
        const tag = document.createElement('span');
        tag.className = 'source-tag';
        tag.innerHTML = `
            ${source}
            <button class="remove-source" onclick="removeSource('${source}')" title="移除">
                <i class="bi bi-x"></i>
            </button>
        `;
        container.appendChild(tag);
    });
    
    console.log(`气象源标签显示已更新: ${selectedSources.length} 个`);
}

// 移除单个气象源
function removeSource(source) {
    // 从选中列表中移除
    selectedSources = selectedSources.filter(s => s !== source);
    
    // 更新复选框状态
    const checkbox = document.getElementById(`source_${source}`);
    if (checkbox) {
        checkbox.checked = false;
    }
    
    // 更新标签显示
    updateSourceTagsDisplay();
    
    // 重新加载数据
    if (currentDataId) {
        console.log(`移除气象源 ${source}，重新加载数据...`);
        onSourceSelectionChange();
    }
    
    console.log(`已移除气象源: ${source}`);
}

function updateSourceCheckboxes() {
    // 更新复选框状态以匹配selectedSources
    document.querySelectorAll('.source-checkbox').forEach(cb => {
        cb.checked = selectedSources.includes(cb.value);
    });
}

function selectAllSources() {
    document.querySelectorAll('.source-checkbox').forEach(cb => cb.checked = true);
    // 立即更新标签显示
    onSourceCheckboxChange();
}

function deselectAllSources() {
    document.querySelectorAll('.source-checkbox').forEach(cb => cb.checked = false);
    // 立即更新标签显示
    onSourceCheckboxChange();
}

// ============================================================================
// 工具函数：错误处理和加载状态
// ============================================================================

function showError(message) {
    const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
    document.getElementById('errorModalBody').textContent = message;
    errorModal.show();
}

function showWarning(message) {
    // 使用浏览器的通知或简单的alert
    // 也可以创建一个自定义的警告模态框
    console.warn(message);
    
    // 创建一个临时的警告提示
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-warning alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.maxWidth = '600px';
    alertDiv.innerHTML = `
        <i class="bi bi-exclamation-triangle-fill me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // 5秒后自动关闭
    setTimeout(() => {
        alertDiv.remove();
    }, 8000);
}

function showLoading(show = true) {
    document.getElementById('loadingOverlay').style.display = show ? 'flex' : 'none';
}

function showDataLoading(show = true) {
    document.getElementById('dataLoadingSpinner').style.display = show ? 'block' : 'none';
}

async function handleApiResponse(response) {
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP ${response.status}: ${response.statusText}`);
    }
    return await response.json();
}

function handleError(context, error) {
    console.error(`${context}:`, error);
    showError(`${context}: ${error.message}`);
}


// ============================================================================
// 数据展示标签页 (任务 9.2)
// ============================================================================

async function displayTimeseriesData() {
    if (!currentDataId) {
        console.error('displayTimeseriesData: currentDataId is null');
        showError('请先加载数据');
        return;
    }
    
    // 如果没有选择气象源，使用所有可用气象源
    const sourcesToUse = (selectedSources && selectedSources.length > 0) 
        ? selectedSources 
        : availableSources;
    
    if (!sourcesToUse || sourcesToUse.length === 0) {
        console.warn('displayTimeseriesData: No sources to display');
        showError('请选择至少一个气象源');
        return;
    }
    
    console.log(`=== 显示时间序列数据 ===`);
    console.log(`Data ID: ${currentDataId}`);
    console.log(`使用气象源 (${sourcesToUse.length}): ${sourcesToUse.join(', ')}`);
    
    showDataLoading(true);
    
    try {
        const includeTrue = true; // 始终显示真实风速
        
        console.log(`Include true: ${includeTrue}`);
        
        const requestBody = {
            data_id: currentDataId,
            sources: sourcesToUse,
            include_true: includeTrue
        };
        
        console.log('发送请求:', requestBody);
        
        const response = await fetch('/api/data/timeseries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        console.log(`响应状态: ${response.status}`);
        
        const data = await handleApiResponse(response);
        
        console.log(`收到数据 - 时间戳数量: ${data.timestamps?.length || 0}`);
        console.log(`数据系列: ${Object.keys(data.series || {}).join(', ')}`);
        
        // 使用Plotly绘制时间序列图
        plotTimeseries(data, sourcesToUse);
        
        console.log('时间序列图表绘制完成');
        
    } catch (error) {
        console.error('displayTimeseriesData error:', error);
        handleError('显示时间序列数据失败', error);
    } finally {
        showDataLoading(false);
    }
}

function plotTimeseries(data, sourcesToUse) {
    console.log('=== 绘制时间序列图表 ===');
    
    const traces = [];
    const colors = generateColors(Object.keys(data.series).length);
    let colorIndex = 0;
    
    // 使用传入的sourcesToUse或selectedSources
    const sources = sourcesToUse || selectedSources || [];
    
    console.log(`绘制气象源 (${sources.length}): ${sources.join(', ')}`);
    
    // 绘制气象源数据
    sources.forEach(source => {
        // 后端返回的键名是 {source}_WS，需要匹配
        const sourceKey = `${source}_WS`;
        const sourceData = data.series[sourceKey] || data.series[source];
        
        if (sourceData) {
            console.log(`添加气象源: ${source}, 键名: ${sourceKey}, 数据点: ${sourceData.length}`);
            traces.push({
                x: data.timestamps,
                y: sourceData,
                type: 'scatter',
                mode: 'lines',
                name: source,
                line: { color: colors[colorIndex++], width: 1.5 }
            });
        } else {
            console.warn(`气象源 ${source} 没有数据（尝试了 ${sourceKey} 和 ${source}）`);
            console.warn(`可用的键: ${Object.keys(data.series).join(', ')}`);
        }
    });
    
    // 绘制true数据
    if (data.series.true) {
        console.log(`添加true (真实风速), 数据点: ${data.series.true.length}`);
        traces.push({
            x: data.timestamps,
            y: data.series.true,
            type: 'scatter',
            mode: 'lines',
            name: 'True (真实风速)',
            line: { color: '#000000', width: 2.5 }
        });
    } else {
        console.warn('true数据不存在');
    }
    
    console.log(`总共绘制 ${traces.length} 条线`);
    
    if (traces.length === 0) {
        console.error('没有数据可以绘制！');
        showError('没有可显示的数据');
        return;
    }
    
    const layout = {
        title: '风速时间序列数据',
        xaxis: {
            title: '时间',
            type: 'date'
        },
        yaxis: {
            title: '风速 (m/s)'
        },
        hovermode: 'x unified',
        legend: {
            orientation: 'h',
            y: -0.2
        },
        margin: { t: 50, b: 100, l: 60, r: 30 }
    };
    
    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        displaylogo: false
    };
    
    Plotly.newPlot('timeseriesChart', traces, layout, config);
}

function generateColors(count) {
    const baseColors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ];
    
    const colors = [];
    for (let i = 0; i < count; i++) {
        colors.push(baseColors[i % baseColors.length]);
    }
    return colors;
}


// ============================================================================
// 统计分析标签页 (任务 9.3)
// ============================================================================

async function displayStatisticalAnalysis() {
    if (!currentDataId) {
        showError('请先加载数据');
        return;
    }
    
    // 更新日期范围显示
    updateAnalysisDateRangeDisplay();
    
    showLoading(true);
    
    try {
        // 并行加载所有统计分析
        await Promise.all([
            displayCorrelationAnalysis(),
            displayErrorMetrics(),
            displayDistributionAnalysis(),
            displayWindSpeedRangeAnalysis(),
            displayBiasDistributionAnalysis()
        ]);
    } catch (error) {
        handleError('加载统计分析失败', error);
    } finally {
        showLoading(false);
    }
}

function updateAnalysisDateRangeDisplay() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const dateRangeText = document.getElementById('analysisDateRangeText');
    
    if (startDate && endDate) {
        dateRangeText.textContent = `分析时间范围: ${startDate} 至 ${endDate}`;
        dateRangeText.classList.remove('text-muted');
        dateRangeText.classList.add('text-primary', 'fw-bold');
    } else {
        dateRangeText.textContent = '请先加载数据';
        dateRangeText.classList.remove('text-primary', 'fw-bold');
        dateRangeText.classList.add('text-muted');
    }
}

async function displayCorrelationAnalysis() {
    if (!currentDataId) {
        document.getElementById('correlationTable').innerHTML = 
            '<div class="alert alert-info">请先加载数据</div>';
        document.getElementById('correlationHeatmap').innerHTML = '';
        return;
    }
    
    // 使用当前选择的气象源
    const sourcesToUse = (selectedSources && selectedSources.length > 0) 
        ? selectedSources 
        : availableSources;
    
    if (!sourcesToUse || sourcesToUse.length === 0) {
        document.getElementById('correlationTable').innerHTML = 
            '<div class="alert alert-warning">请选择至少一个气象源</div>';
        document.getElementById('correlationHeatmap').innerHTML = '';
        return;
    }
    
    console.log(`相关性分析 - 使用气象源 (${sourcesToUse.length}): ${sourcesToUse.join(', ')}`);
    
    try {
        const response = await fetch('/api/analysis/correlation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data_id: currentDataId,
                sources: sourcesToUse
            })
        });
        
        const data = await handleApiResponse(response);
        
        // 显示相关系数表格
        displayCorrelationTable(data.correlations);
        
        // 显示相关性热力图
        plotCorrelationHeatmap(data.matrix, data.matrix_labels);
        
    } catch (error) {
        console.error('相关性分析失败:', error);
        document.getElementById('correlationTable').innerHTML = 
            `<div class="alert alert-danger">加载失败: ${error.message}</div>`;
    }
}

function displayCorrelationTable(correlations) {
    // 安全地格式化数值
    const formatValue = (value) => {
        if (value === null || value === undefined || isNaN(value)) {
            return 'N/A';
        }
        return value.toFixed(4);
    };
    
    const tableHtml = `
        <table class="table table-striped table-hover">
            <thead>
                <tr>
                    <th>气象源</th>
                    <th>相关系数</th>
                </tr>
            </thead>
            <tbody>
                ${correlations.map(item => `
                    <tr>
                        <td>${item.source || 'Unknown'}</td>
                        <td>${formatValue(item.correlation)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    document.getElementById('correlationTable').innerHTML = tableHtml;
}

function plotCorrelationHeatmap(matrix, sourceNames) {
    const trace = {
        z: matrix,
        x: sourceNames,
        y: sourceNames,
        type: 'heatmap',
        colorscale: 'RdBu',
        zmid: 0,
        text: matrix.map(row => row.map(val => val.toFixed(3))),
        texttemplate: '%{text}',
        textfont: { size: 10 },
        hovertemplate: '%{y} vs %{x}<br>相关系数: %{z:.4f}<extra></extra>'
    };
    
    const layout = {
        title: '气象源相关性矩阵',
        xaxis: { side: 'bottom' },
        yaxis: { autorange: 'reversed' },
        margin: { t: 50, b: 100, l: 100, r: 30 }
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('correlationHeatmap', [trace], layout, config);
}

async function displayErrorMetrics() {
    if (!currentDataId) {
        document.getElementById('errorMetricsTable').innerHTML = 
            '<div class="alert alert-info">请先加载数据</div>';
        document.getElementById('errorMetricsChart').innerHTML = '';
        return;
    }
    
    // 使用当前选择的气象源
    const sourcesToUse = (selectedSources && selectedSources.length > 0) 
        ? selectedSources 
        : availableSources;
    
    if (!sourcesToUse || sourcesToUse.length === 0) {
        document.getElementById('errorMetricsTable').innerHTML = 
            '<div class="alert alert-warning">请选择至少一个气象源</div>';
        document.getElementById('errorMetricsChart').innerHTML = '';
        return;
    }
    
    console.log(`误差指标分析 - 使用气象源 (${sourcesToUse.length}): ${sourcesToUse.join(', ')}`);
    
    try {
        const response = await fetch('/api/analysis/error_metrics', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data_id: currentDataId,
                sources: sourcesToUse
            })
        });
        
        const data = await handleApiResponse(response);
        
        // 显示误差指标表格
        displayErrorMetricsTable(data.metrics);
        
        // 显示误差对比柱状图
        plotErrorMetricsChart(data.metrics);
        
    } catch (error) {
        console.error('误差指标分析失败:', error);
        document.getElementById('errorMetricsTable').innerHTML = 
            `<div class="alert alert-danger">加载失败: ${error.message}</div>`;
    }
}

function displayErrorMetricsTable(metrics) {
    // 安全地格式化数值
    const formatValue = (value) => {
        if (value === null || value === undefined || isNaN(value)) {
            return 'N/A';
        }
        return value.toFixed(4);
    };
    
    const tableHtml = `
        <table class="table table-striped table-hover">
            <thead>
                <tr>
                    <th>数据源</th>
                    <th>RMSE</th>
                    <th>MAE</th>
                </tr>
            </thead>
            <tbody>
                ${metrics.map(item => `
                    <tr>
                        <td>${item.source || 'Unknown'}</td>
                        <td>${formatValue(item.RMSE || item.rmse)}</td>
                        <td>${formatValue(item.MAE || item.mae)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    document.getElementById('errorMetricsTable').innerHTML = tableHtml;
}

function plotErrorMetricsChart(metrics) {
    // 安全地获取值，处理大小写和undefined
    const getValue = (item, key1, key2) => {
        const value = item[key1] || item[key2];
        return (value !== null && value !== undefined && !isNaN(value)) ? value : 0;
    };
    
    const sources = metrics.map(m => m.source || 'Unknown');
    
    const trace1 = {
        x: sources,
        y: metrics.map(m => getValue(m, 'RMSE', 'rmse')),
        name: 'RMSE',
        type: 'bar',
        marker: { color: '#FF6B6B' }
    };
    
    const trace2 = {
        x: sources,
        y: metrics.map(m => getValue(m, 'MAE', 'mae')),
        name: 'MAE',
        type: 'bar',
        marker: { color: '#4ECDC4' }
    };
    
    const layout = {
        title: '误差指标对比',
        xaxis: { title: '数据源' },
        yaxis: { title: '误差值' },
        barmode: 'group',
        margin: { t: 50, b: 100, l: 60, r: 30 }
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('errorMetricsChart', [trace1, trace2], layout, config);
}

async function displayDistributionAnalysis() {
    if (!currentDataId) {
        document.getElementById('statMean').textContent = '--';
        document.getElementById('statMedian').textContent = '--';
        document.getElementById('statStd').textContent = '--';
        document.getElementById('statMin').textContent = '--';
        document.getElementById('statMax').textContent = '--';
        document.getElementById('distributionHistogram').innerHTML = 
            '<div class="alert alert-info text-center">请先加载数据</div>';
        document.getElementById('distributionBoxplot').innerHTML = '';
        return;
    }
    
    try {
        const response = await fetch('/api/analysis/distribution', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data_id: currentDataId,
                data_type: 'true'
            })
        });
        
        const data = await handleApiResponse(response);
        
        console.log('Distribution data received:', data);
        
        // 显示统计量卡片
        displayDistributionStats(data.stats);
        
        // 显示直方图
        if (data.histogram) {
            plotDistributionHistogram(data.histogram);
        }
        
        // 显示箱线图（使用统计数据生成）
        if (data.stats) {
            plotDistributionBoxplot(data.stats);
        }
        
    } catch (error) {
        console.error('数据分布分析失败:', error);
        document.getElementById('distributionHistogram').innerHTML = 
            `<div class="alert alert-danger">加载失败: ${error.message}</div>`;
    }
}

function displayDistributionStats(stats) {
    // 安全地格式化数值
    const formatValue = (value) => {
        if (value === null || value === undefined || isNaN(value)) {
            return '--';
        }
        return value.toFixed(2);
    };
    
    document.getElementById('statMean').textContent = formatValue(stats.mean);
    document.getElementById('statMedian').textContent = formatValue(stats.median);
    document.getElementById('statStd').textContent = formatValue(stats.std);
    document.getElementById('statMin').textContent = formatValue(stats.min);
    document.getElementById('statMax').textContent = formatValue(stats.max);
}

function plotDistributionHistogram(histData) {
    console.log('Plotting histogram with data:', histData);
    
    // 检查数据结构
    if (!histData || !histData.bins || !histData.counts) {
        console.error('Invalid histogram data structure:', histData);
        document.getElementById('distributionHistogram').innerHTML = 
            '<div class="alert alert-warning">直方图数据格式错误</div>';
        return;
    }
    
    // 计算每个区间的中心点作为x值
    const bins = histData.bins;
    const counts = histData.counts;
    const binCenters = [];
    
    for (let i = 0; i < bins.length - 1; i++) {
        binCenters.push((bins[i] + bins[i + 1]) / 2);
    }
    
    const trace = {
        x: binCenters,
        y: counts,
        type: 'bar',
        marker: { color: '#1f77b4' },
        name: '真实风速'
    };
    
    const layout = {
        title: '风速分布直方图',
        xaxis: { title: '风速 (m/s)' },
        yaxis: { title: '频数' },
        margin: { t: 50, b: 60, l: 60, r: 30 }
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('distributionHistogram', [trace], layout, config);
}

function plotDistributionBoxplot(stats) {
    console.log('Plotting boxplot with stats:', stats);
    
    // 检查数据
    if (!stats) {
        console.error('No stats data for boxplot');
        document.getElementById('distributionBoxplot').innerHTML = 
            '<div class="alert alert-warning">箱线图数据不可用</div>';
        return;
    }
    
    // 使用统计数据创建箱线图
    const trace = {
        type: 'box',
        name: '真实风速',
        marker: { color: '#2ca02c' },
        boxmean: 'sd',
        // 使用统计数据手动构建箱线图
        median: [stats.median],
        q1: [stats.q25],
        q3: [stats.q75],
        lowerfence: [stats.min],
        upperfence: [stats.max],
        mean: [stats.mean],
        sd: [stats.std]
    };
    
    const layout = {
        title: '风速箱线图',
        yaxis: { title: '风速 (m/s)' },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        showlegend: false
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('distributionBoxplot', [trace], layout, config);
}

async function displayWindSpeedRangeAnalysis() {
    if (!currentDataId) {
        document.getElementById('windSpeedRangeTable').innerHTML = 
            '<div class="alert alert-info">请先加载数据</div>';
        document.getElementById('windSpeedRangeChart').innerHTML = '';
        return;
    }
    
    // 使用当前选择的气象源
    const sourcesToUse = (selectedSources && selectedSources.length > 0) 
        ? selectedSources 
        : availableSources;
    
    if (!sourcesToUse || sourcesToUse.length === 0) {
        document.getElementById('windSpeedRangeTable').innerHTML = 
            '<div class="alert alert-warning">请选择至少一个气象源</div>';
        document.getElementById('windSpeedRangeChart').innerHTML = '';
        return;
    }
    
    console.log(`风速区间分析 - 使用气象源 (${sourcesToUse.length}): ${sourcesToUse.join(', ')}`);
    
    try {
        const response = await fetch('/api/analysis/wind_speed_range', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data_id: currentDataId,
                sources: sourcesToUse
            })
        });
        
        const data = await handleApiResponse(response);
        
        // 显示风速区间表格
        displayWindSpeedRangeTable(data.range_analysis);
        
        // 显示风速区间对比图
        plotWindSpeedRangeChart(data.range_analysis, data.ranges);
        
    } catch (error) {
        console.error('风速区间分析失败:', error);
        document.getElementById('windSpeedRangeTable').innerHTML = 
            `<div class="alert alert-danger">加载失败: ${error.message}</div>`;
    }
}

function displayWindSpeedRangeTable(rangeAnalysis) {
    // 安全地格式化数值
    const formatValue = (value) => {
        if (value === null || value === undefined || isNaN(value)) {
            return 'N/A';
        }
        return value.toFixed(3);
    };
    
    // 获取所有气象源
    const sources = Object.keys(rangeAnalysis);
    
    // 获取所有区间并按照正确的顺序排序
    let ranges = sources.length > 0 ? Object.keys(rangeAnalysis[sources[0]]) : [];
    
    // 定义正确的区间顺序
    const rangeOrder = ['0-3', '3-6', '6-10', '10-15', '15-+'];
    
    // 按照预定义的顺序排序区间
    ranges = ranges.sort((a, b) => {
        const indexA = rangeOrder.indexOf(a);
        const indexB = rangeOrder.indexOf(b);
        // 如果区间在预定义列表中，按照列表顺序排序
        if (indexA !== -1 && indexB !== -1) {
            return indexA - indexB;
        }
        // 如果区间不在预定义列表中，保持原顺序
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
    });
    
    const tableHtml = `
        <table class="table table-striped table-hover table-sm">
            <thead>
                <tr>
                    <th style="width: 120px; font-size: 0.85rem;">气象源</th>
                    ${ranges.map(range => `<th class="text-center">${range}</th>`).join('')}
                </tr>
            </thead>
            <tbody>
                ${sources.map(source => `
                    <tr>
                        <td style="width: 120px; font-size: 0.8rem; word-wrap: break-word; word-break: break-word;">
                            <strong>${source}</strong>
                        </td>
                        ${ranges.map(range => {
                            const metrics = rangeAnalysis[source][range];
                            return `<td class="text-center">
                                <small style="font-size: 0.75rem;">
                                    RMSE: ${formatValue(metrics.rmse)}<br>
                                    MAE: ${formatValue(metrics.mae)}<br>
                                    样本: ${metrics.count || 0}
                                </small>
                            </td>`;
                        }).join('')}
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    document.getElementById('windSpeedRangeTable').innerHTML = tableHtml;
}

function plotWindSpeedRangeChart(rangeAnalysis, ranges) {
    const sources = Object.keys(rangeAnalysis);
    
    // 定义正确的区间顺序
    const rangeOrder = ['0-3', '3-6', '6-10', '10-15', '15-+'];
    
    // 按照预定义的顺序排序区间
    const sortedRanges = ranges.sort((a, b) => {
        const indexA = rangeOrder.indexOf(a);
        const indexB = rangeOrder.indexOf(b);
        // 如果区间在预定义列表中，按照列表顺序排序
        if (indexA !== -1 && indexB !== -1) {
            return indexA - indexB;
        }
        // 如果区间不在预定义列表中，保持原顺序
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
    });
    
    // 为每个气象源创建一条线
    const traces = sources.map(source => {
        const rmseValues = sortedRanges.map(range => {
            const rmse = rangeAnalysis[source][range].rmse;
            // 如果值为null或undefined，返回null（Plotly会跳过这些点）
            return (rmse !== null && rmse !== undefined && !isNaN(rmse)) ? rmse : null;
        });
        
        return {
            x: sortedRanges,
            y: rmseValues,
            type: 'scatter',
            mode: 'lines+markers',
            name: source,
            line: { width: 2 },
            marker: { size: 8 },
            connectgaps: false  // 不连接缺失数据点
        };
    });
    
    const layout = {
        title: '不同风速区间的RMSE对比',
        xaxis: { title: '风速区间 (m/s)' },
        yaxis: { title: 'RMSE' },
        hovermode: 'x unified',
        margin: { t: 50, b: 60, l: 60, r: 30 },
        legend: {
            orientation: 'v',  // 垂直排列
            x: 1.02,  // 放在图表右侧外部
            y: 1,  // 顶部对齐
            xanchor: 'left',  // 从左边开始
            yanchor: 'top',  // 从顶部开始
            bgcolor: 'rgba(255, 255, 255, 0.9)',  // 半透明白色背景
            bordercolor: '#ddd',
            borderwidth: 1,
            font: {
                size: 10  // 减小字体大小
            },
            itemsizing: 'constant',  // 固定图例项大小
            itemwidth: 30  // 减小图例项宽度
        }
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('windSpeedRangeChart', traces, layout, config);
}

async function displayBiasDistributionAnalysis() {
    if (!currentDataId) {
        document.getElementById('biasStatsTable').innerHTML = 
            '<div class="alert alert-info">请先加载数据</div>';
        document.getElementById('biasDistributionHistogram').innerHTML = '';
        document.getElementById('biasBoxplot').innerHTML = '';
        return;
    }
    
    // 使用当前选择的气象源
    const sourcesToUse = (selectedSources && selectedSources.length > 0) 
        ? selectedSources 
        : availableSources;
    
    if (!sourcesToUse || sourcesToUse.length === 0) {
        document.getElementById('biasStatsTable').innerHTML = 
            '<div class="alert alert-warning">请选择至少一个气象源</div>';
        document.getElementById('biasDistributionHistogram').innerHTML = '';
        document.getElementById('biasBoxplot').innerHTML = '';
        return;
    }
    
    console.log(`偏差分布分析 - 使用气象源 (${sourcesToUse.length}): ${sourcesToUse.join(', ')}`);
    
    try {
        const response = await fetch('/api/analysis/bias_distribution', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data_id: currentDataId,
                sources: sourcesToUse
            })
        });
        
        const data = await handleApiResponse(response);
        
        console.log('偏差分布数据:', data);
        
        // 显示偏差统计表格
        displayBiasStatsTable(data.bias_distribution);
        
        // 显示偏差分布直方图
        plotBiasDistributionHistogram(data.bias_distribution);
        
        // 显示偏差箱型图
        plotBiasBoxplot(data.bias_distribution);
        
    } catch (error) {
        console.error('偏差分布分析失败:', error);
        document.getElementById('biasStatsTable').innerHTML = 
            `<div class="alert alert-danger">加载失败: ${error.message}</div>`;
    }
}

function displayBiasStatsTable(biasDistribution) {
    // 安全地格式化数值
    const formatValue = (value) => {
        if (value === null || value === undefined || isNaN(value)) {
            return 'N/A';
        }
        return value.toFixed(4);
    };
    
    const sources = Object.keys(biasDistribution);
    
    const tableHtml = `
        <table class="table table-striped table-hover">
            <thead>
                <tr>
                    <th>气象源</th>
                    <th>平均偏差</th>
                    <th>偏差标准差</th>
                    <th>最小偏差</th>
                    <th>25%分位</th>
                    <th>中位数</th>
                    <th>75%分位</th>
                    <th>最大偏差</th>
                    <th>样本数</th>
                </tr>
            </thead>
            <tbody>
                ${sources.map(source => {
                    const stats = biasDistribution[source];
                    return `
                        <tr>
                            <td><strong>${source}</strong></td>
                            <td>${formatValue(stats.mean_bias)}</td>
                            <td>${formatValue(stats.std_bias)}</td>
                            <td>${formatValue(stats.min_bias)}</td>
                            <td>${formatValue(stats.q25)}</td>
                            <td>${formatValue(stats.q50)}</td>
                            <td>${formatValue(stats.q75)}</td>
                            <td>${formatValue(stats.max_bias)}</td>
                            <td>${stats.count || 0}</td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
    document.getElementById('biasStatsTable').innerHTML = tableHtml;
}

function plotBiasDistributionHistogram(biasDistribution) {
    const sources = Object.keys(biasDistribution);
    
    // 为每个气象源创建一个直方图trace
    const traces = sources.map((source, index) => {
        const biasData = biasDistribution[source].bias;
        
        return {
            x: biasData,
            type: 'histogram',
            name: source,
            opacity: 0.7,
            nbinsx: 30,  // 设置直方图的柱数
            marker: {
                line: {
                    color: 'white',
                    width: 1
                }
            }
        };
    });
    
    const layout = {
        title: '偏差分布直方图（预测值 - 真实值）',
        xaxis: { 
            title: '偏差 (m/s)',
            zeroline: true,
            zerolinecolor: 'red',
            zerolinewidth: 2
        },
        yaxis: { title: '频数' },
        barmode: 'overlay',  // 重叠显示
        hovermode: 'closest',
        margin: { t: 50, b: 60, l: 60, r: 30 },
        showlegend: true,
        legend: {
            orientation: 'h',
            y: -0.2
        }
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('biasDistributionHistogram', traces, layout, config);
}

function plotBiasBoxplot(biasDistribution) {
    const sources = Object.keys(biasDistribution);
    
    // 为每个气象源创建一个箱型图trace
    const traces = sources.map(source => {
        const biasData = biasDistribution[source].bias;
        
        return {
            y: biasData,
            type: 'box',
            name: source,
            boxmean: 'sd',  // 显示均值和标准差
            marker: {
                outliercolor: 'rgba(219, 64, 82, 0.6)',
                line: {
                    outliercolor: 'rgba(219, 64, 82, 1.0)',
                    outlierwidth: 2
                }
            }
        };
    });
    
    const layout = {
        title: '偏差箱型图（预测值 - 真实值）',
        yaxis: { 
            title: '偏差 (m/s)',
            zeroline: true,
            zerolinecolor: 'red',
            zerolinewidth: 2
        },
        hovermode: 'closest',
        margin: { t: 50, b: 100, l: 60, r: 30 },
        showlegend: false
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('biasBoxplot', traces, layout, config);
}

// ============================================================================
// 特征工程标签页 (任务 9.4)
// ============================================================================

function selectAllFeatureGroups() {
    document.querySelectorAll('.feature-group-check').forEach(cb => cb.checked = true);
}

function deselectAllFeatureGroups() {
    document.querySelectorAll('.feature-group-check').forEach(cb => cb.checked = false);
}

async function onGenerateFeatures() {
    if (!currentDataId) {
        showError('请先加载数据');
        return;
    }
    
    const selectedGroups = Array.from(document.querySelectorAll('.feature-group-check:checked'))
        .map(cb => cb.value);
    
    if (selectedGroups.length === 0) {
        showError('请至少选择一个特征组');
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/features/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data_id: currentDataId,
                feature_groups: selectedGroups
            })
        });
        
        const data = await handleApiResponse(response);
        currentFeatureId = data.feature_id;
        
        console.log(`特征已生成，feature_id: ${currentFeatureId}`);
        console.log(`特征数量: ${data.feature_names.length}`);
        
        // 显示特征列表
        displayFeaturesList(data.feature_names, data.groups);
        
        showSuccess(`成功生成 ${data.feature_names.length} 个特征`);
        
    } catch (error) {
        handleError('生成特征失败', error);
    } finally {
        showLoading(false);
    }
}

function displayFeaturesList(featureNames, groups) {
    let html = '<div class="p-3">';
    html += `<p class="text-muted">共生成 ${featureNames.length} 个特征</p>`;
    
    // 按组显示特征
    for (const [groupName, features] of Object.entries(groups)) {
        if (features.length > 0) {
            html += `<h6 class="mt-3">${getGroupDisplayName(groupName)} (${features.length})</h6>`;
            html += '<ul class="list-unstyled ms-3">';
            features.forEach(feature => {
                html += `<li><small><code>${feature}</code></small></li>`;
            });
            html += '</ul>';
        }
    }
    
    html += '</div>';
    document.getElementById('featuresList').innerHTML = html;
}

function getGroupDisplayName(groupName) {
    const names = {
        'raw_meteorological': '原始气象要素',
        'time_features': '时间特征',
        'business_features': '业务特征',
        'statistical_features': '统计特征',
        'difference_features': '差值特征',
        'interaction_features': '交互特征'
    };
    return names[groupName] || groupName;
}

function showSuccess(message) {
    // 简单的成功提示，可以使用toast或alert
    console.log('成功:', message);
    // 可以添加Bootstrap toast组件来显示成功消息
}


// ============================================================================
// 模型训练标签页 (任务 9.5)
// ============================================================================

function onModelTypeChange(event) {
    const modelType = event.target.value;
    
    // 根据模型类型显示/隐藏参数
    const nEstimatorsParam = document.getElementById('paramNEstimators');
    const maxDepthParam = document.getElementById('paramMaxDepth');
    
    if (modelType === 'linear_regression') {
        nEstimatorsParam.style.display = 'none';
        maxDepthParam.style.display = 'none';
    } else if (modelType === 'decision_tree') {
        nEstimatorsParam.style.display = 'none';
        maxDepthParam.style.display = 'block';
    } else if (modelType === 'random_forest') {
        nEstimatorsParam.style.display = 'block';
        maxDepthParam.style.display = 'block';
    }
}

async function onTrainModel() {
    if (!currentStationId) {
        showError('请先选择场站');
        return;
    }
    
    // 检查是否选择了气象源
    if (!selectedSources || selectedSources.length === 0) {
        showError('请先选择至少一个气象源');
        return;
    }
    
    const modelType = document.querySelector('input[name="modelType"]:checked').value;
    const testSize = parseFloat(document.getElementById('testSize').value);
    const predictStartDate = document.getElementById('predictStartDate').value;
    const predictEndDate = document.getElementById('predictEndDate').value;
    const trainDays = parseInt(document.getElementById('trainDays').value);
    const resolution = document.getElementById('resolutionSelect').value;
    
    // 验证预测数据范围
    if (!predictStartDate || !predictEndDate) {
        showError('请设置预测时间范围');
        return;
    }
    
    if (new Date(predictStartDate) >= new Date(predictEndDate)) {
        showError('预测开始日期必须早于结束日期');
        return;
    }
    
    // 计算训练数据范围
    const predictStart = new Date(predictStartDate);
    const trainEndDate = new Date(predictStart);
    trainEndDate.setDate(trainEndDate.getDate() - 1); // 预测开始日期的前一天
    
    const trainStartDate = new Date(trainEndDate);
    trainStartDate.setDate(trainStartDate.getDate() - trainDays + 1); // 往前推trainDays天
    
    const trainStartStr = formatDateToYYYYMMDD(trainStartDate);
    const trainEndStr = formatDateToYYYYMMDD(trainEndDate);
    
    console.log(`=== 开始训练模型 ===`);
    console.log(`场站: ${currentStationId}`);
    console.log(`训练数据范围: ${trainStartStr} 到 ${trainEndStr} (${trainDays}天)`);
    console.log(`预测数据范围: ${predictStartDate} 到 ${predictEndDate}`);
    console.log(`验证集比例: ${testSize}`);
    console.log(`时间分辨率: ${resolution}`);
    console.log(`气象源: ${selectedSources.join(', ')}`);
    
    const params = {
        test_size: testSize
    };
    
    if (modelType === 'random_forest') {
        params.n_estimators = parseInt(document.getElementById('nEstimators').value);
        params.max_depth = parseInt(document.getElementById('maxDepth').value);
    } else if (modelType === 'decision_tree') {
        params.max_depth = parseInt(document.getElementById('maxDepth').value);
    }
    
    // 获取选中的特征组
    const selectedFeatureGroups = Array.from(document.querySelectorAll('.feature-group-check:checked'))
        .map(cb => cb.value);
    
    if (selectedFeatureGroups.length === 0) {
        showError('请至少选择一个特征组');
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/model/train', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                station_id: currentStationId,
                model_type: modelType,
                params: params,
                train_start_date: trainStartStr,
                train_end_date: trainEndStr,
                predict_start_date: predictStartDate,
                predict_end_date: predictEndDate,
                resolution: resolution,
                sources: selectedSources,
                feature_groups: selectedFeatureGroups
            })
        });
        
        const data = await handleApiResponse(response);
        currentModelId = data.model_id;
        
        console.log(`模型已训练，model_id: ${currentModelId}`);
        console.log(`训练数据: ${trainStartStr} 到 ${trainEndStr}`);
        console.log(`训练集大小: ${data.train_size}, 验证集大小: ${data.test_size}`);
        console.log(`预测数据: ${predictStartDate} 到 ${predictEndDate}`);
        
        // 显示评估指标
        displayModelMetrics(data.metrics);
        
        // 显示预测vs真实对比图
        plotPredictionComparison(data.predictions, data.actual, data.timestamps);
        
        // 获取并显示特征重要性（所有模型类型都支持）
        await displayFeatureImportance();
        
        // 显示成功消息
        const trainSizePercent = ((1 - testSize) * 100).toFixed(0);
        const testSizePercent = (testSize * 100).toFixed(0);
        showSuccess(`模型训练完成！训练集: ${data.train_size}条 (${trainSizePercent}%), 验证集: ${data.test_size}条 (${testSizePercent}%)`);
        
    } catch (error) {
        handleError('模型训练失败', error);
    } finally {
        showLoading(false);
    }
}

function displayModelMetrics(metrics) {
    // 隐藏使用提示
    const tip = document.getElementById('modelTrainingTip');
    if (tip) {
        tip.style.display = 'none';
    }
    
    document.getElementById('metricRMSE').textContent = metrics.rmse.toFixed(4);
    document.getElementById('metricMAE').textContent = metrics.mae.toFixed(4);
    document.getElementById('metricSpearman').textContent = metrics.spearman_corr.toFixed(4);
}

function plotPredictionComparison(predictions, actual, timestamps) {
    const trace1 = {
        x: timestamps,
        y: actual,
        type: 'scatter',
        mode: 'lines',
        name: '真实值',
        line: { color: '#000000', width: 2 }
    };
    
    const trace2 = {
        x: timestamps,
        y: predictions,
        type: 'scatter',
        mode: 'lines',
        name: '预测值',
        line: { color: '#FF6B6B', width: 2, dash: 'dash' }
    };
    
    const layout = {
        title: '预测值 vs 真实值',
        xaxis: { title: '时间', type: 'date' },
        yaxis: { title: '风速 (m/s)' },
        hovermode: 'x unified',
        margin: { t: 50, b: 60, l: 60, r: 30 }
    };
    
    const config = { responsive: true, displaylogo: false };
    
    Plotly.newPlot('predictionChart', [trace1, trace2], layout, config);
}

async function displayFeatureImportance() {
    if (!currentModelId) {
        console.error('Missing model_id');
        return;
    }
    
    try {
        const response = await fetch('/api/model/feature_importance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_id: currentModelId,
                top_n: 20
            })
        });
        
        const data = await handleApiResponse(response);
        
        console.log(`获取到 ${data.importance.length} 个特征的重要性`);
        
        // 显示特征重要性柱状图
        plotFeatureImportance(data.importance);
        
    } catch (error) {
        console.error('获取特征重要性失败:', error);
        // 显示错误信息
        document.getElementById('featureImportanceChart').innerHTML = 
            `<div class="alert alert-danger m-3">获取特征重要性失败: ${error.message}</div>`;
    }
}

function plotFeatureImportance(importance) {
    // 验证数据
    if (!importance || importance.length === 0) {
        console.error('No feature importance data to display');
        document.getElementById('featureImportanceChart').innerHTML = 
            '<div class="alert alert-warning m-3">没有特征重要性数据</div>';
        return;
    }
    
    console.log(`Plotting feature importance for ${importance.length} features`);
    
    // 取前20个最重要的特征
    const top20 = importance.slice(0, 20);
    
    // 验证数据格式
    if (!top20[0].feature || top20[0].importance === undefined) {
        console.error('Invalid feature importance data format:', top20[0]);
        document.getElementById('featureImportanceChart').innerHTML = 
            '<div class="alert alert-danger m-3">特征重要性数据格式错误</div>';
        return;
    }
    
    // 获取当前模型类型
    const modelType = document.querySelector('input[name="modelType"]:checked')?.value || 'random_forest';
    
    // 根据模型类型设置标题和x轴标签
    let chartTitle = `特征重要性 (Top ${top20.length})`;
    let xAxisTitle = '重要性';
    
    if (modelType === 'linear_regression') {
        chartTitle = `特征权重 (Top ${top20.length})`;
        xAxisTitle = '系数绝对值';
    }
    
    const trace = {
        x: top20.map(item => item.importance),
        y: top20.map(item => item.feature),
        type: 'bar',
        orientation: 'h',
        marker: { color: '#4ECDC4' },
        text: top20.map(item => item.importance.toFixed(4)),
        textposition: 'outside'
    };
    
    const layout = {
        title: chartTitle,
        xaxis: { 
            title: xAxisTitle,
            range: [0, Math.max(...top20.map(item => item.importance)) * 1.1]
        },
        yaxis: { 
            title: '特征',
            autorange: 'reversed',
            tickfont: { size: 10 }
        },
        margin: { t: 50, b: 60, l: 250, r: 80 },
        height: Math.max(500, top20.length * 25)
    };
    
    const config = { 
        responsive: true, 
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d']
    };
    
    try {
        Plotly.newPlot('featureImportanceChart', [trace], layout, config);
        console.log('Feature importance chart plotted successfully');
    } catch (error) {
        console.error('Error plotting feature importance:', error);
        document.getElementById('featureImportanceChart').innerHTML = 
            `<div class="alert alert-danger m-3">绘制图表失败: ${error.message}</div>`;
    }
}


// ============================================================================
// 时间范围分析选项 (任务 9.6)
// ============================================================================

// 时间范围分析功能已集成在日期选择器中
// 用户可以通过startDate和endDate选择自定义时间范围
// 当日期范围变更后，点击"应用设置"按钮会重新加载数据并执行分析

function setPresetDateRange(preset) {
    const endDate = new Date();
    let startDate = new Date();
    
    switch(preset) {
        case 'last7days':
            startDate.setDate(endDate.getDate() - 7);
            break;
        case 'last15days':
            startDate.setDate(endDate.getDate() - 15);
            break;
        case 'last30days':
            startDate.setDate(endDate.getDate() - 30);
            break;
        case 'lastQuarter':
            startDate.setMonth(endDate.getMonth() - 3);
            break;
        case 'lastYear':
            startDate.setFullYear(endDate.getFullYear() - 1);
            break;
    }
    
    document.getElementById('startDate').valueAsDate = startDate;
    document.getElementById('endDate').valueAsDate = endDate;
}

// 设置默认预测日期范围（2026-01-01 到 2026-01-31）
function setDefaultPredictDateRange() {
    const predictStartDate = new Date('2026-01-01');
    const predictEndDate = new Date('2026-01-31');
    
    document.getElementById('predictStartDate').value = '2026-01-01';
    document.getElementById('predictEndDate').value = '2026-01-31';
    
    console.log(`设置默认预测日期范围: 2026-01-01 到 2026-01-31`);
}

// 显示训练日期范围信息
function showTrainDateInfo() {
    const predictStartDateStr = document.getElementById('predictStartDate').value;
    const predictEndDateStr = document.getElementById('predictEndDate').value;
    const trainDays = parseInt(document.getElementById('trainDays').value);
    
    if (!predictStartDateStr) {
        showError('请先设置预测开始日期');
        return;
    }
    
    // 计算训练数据范围
    const predictStartDate = new Date(predictStartDateStr);
    const trainEndDate = new Date(predictStartDate);
    trainEndDate.setDate(trainEndDate.getDate() - 1); // 预测开始日期的前一天
    
    const trainStartDate = new Date(trainEndDate);
    trainStartDate.setDate(trainStartDate.getDate() - trainDays + 1); // 往前推trainDays天
    
    const trainStartStr = formatDateToYYYYMMDD(trainStartDate);
    const trainEndStr = formatDateToYYYYMMDD(trainEndDate);
    
    const testSize = parseFloat(document.getElementById('testSize').value);
    const trainSize = Math.round(trainDays * (1 - testSize));
    const validSize = Math.round(trainDays * testSize);
    
    // 计算预测天数
    const predictStart = new Date(predictStartDateStr);
    const predictEnd = new Date(predictEndDateStr);
    const predictDays = Math.ceil((predictEnd - predictStart) / (1000 * 60 * 60 * 24)) + 1;
    
    const message = `
        <div class="alert alert-info">
            <h6><i class="bi bi-info-circle"></i> 训练数据范围</h6>
            <p class="mb-2"><strong>训练数据时间范围：</strong><br>
            ${trainStartStr} 至 ${trainEndStr} (共 ${trainDays} 天)</p>
            <p class="mb-2"><strong>数据划分：</strong><br>
            训练集: 约 ${trainSize} 天 (${(1-testSize)*100}%)<br>
            验证集: 约 ${validSize} 天 (${testSize*100}%)</p>
            <p class="mb-2"><strong>预测时间范围：</strong><br>
            ${predictStartDateStr} 至 ${predictEndDateStr} (共 ${predictDays} 天)</p>
            <hr class="my-2">
            <small class="text-muted"><i class="bi bi-lightbulb"></i> 点击"训练模型"按钮将自动从数据库加载数据</small>
        </div>
    `;
    
    // 创建临时提示框
    const alertDiv = document.createElement('div');
    alertDiv.className = 'position-fixed top-50 start-50 translate-middle';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.maxWidth = '500px';
    alertDiv.innerHTML = `
        <div class="card shadow-lg">
            <div class="card-body">
                ${message}
                <button class="btn btn-sm btn-primary w-100" onclick="this.closest('.position-fixed').remove()">
                    确定
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(alertDiv);
}

function setDefaultTrainDateRange() {
    // 这个函数已被新的逻辑替代，保留以防其他地方调用
    console.warn('setDefaultTrainDateRange is deprecated, use setDefaultPredictDateRange instead');
}

// ============================================================================
// 导出功能 (任务 9.7)
// ============================================================================

async function exportChart(chartId) {
    try {
        const chartElement = document.getElementById(chartId);
        
        if (!chartElement || !chartElement.data) {
            showError('没有可导出的图表');
            return;
        }
        
        // 使用Plotly的下载图片功能
        Plotly.downloadImage(chartElement, {
            format: 'png',
            width: 1200,
            height: 800,
            filename: `${chartId}_${currentStationId}_${Date.now()}`
        });
        
        console.log(`图表 ${chartId} 已导出`);
        
    } catch (error) {
        handleError('导出图表失败', error);
    }
}

async function exportCSV(dataType) {
    if (!currentDataId) {
        showError('请先加载数据');
        return;
    }
    
    try {
        const response = await fetch('/api/export/csv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data_id: currentDataId,
                data_type: dataType
            })
        });
        
        if (!response.ok) {
            throw new Error('导出失败');
        }
        
        // 下载文件
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${currentStationId}_${dataType}_${Date.now()}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        console.log(`CSV文件已导出: ${dataType}`);
        
    } catch (error) {
        handleError('导出CSV失败', error);
    }
}

// ============================================================================
// 标签页切换处理 (任务 9.8)
// ============================================================================

function onTabChange(event) {
    const targetId = event.target.getAttribute('data-bs-target');
    
    console.log(`切换到标签页: ${targetId}`);
    
    // 根据标签页加载相应数据
    if (targetId === '#analysis-panel' && currentDataId) {
        displayStatisticalAnalysis();
    } else if (targetId === '#model-panel' && currentDataId) {
        // 切换到模型训练标签页时，自动设置默认训练日期范围
        const trainStartDate = document.getElementById('trainStartDate').value;
        const trainEndDate = document.getElementById('trainEndDate').value;
        
        // 如果还没有设置训练日期范围，则自动设置
        if (!trainStartDate || !trainEndDate) {
            setDefaultTrainDateRange();
        }
    }
}
