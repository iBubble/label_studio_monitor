document.addEventListener('DOMContentLoaded', () => {
    const subnetSelect = document.getElementById('subnetSelect');
    const scanBtn = document.getElementById('scanBtn');
    
    const resultsBody = document.getElementById('resultsBody');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const progressPercentage = document.getElementById('progressPercentage');
    
    // Stats Elements
    const statTotal = document.getElementById('statTotal');
    const statScanned = document.getElementById('statScanned');
    const stat8080 = document.getElementById('stat8080');
    const statLabelStudio = document.getElementById('statLabelStudio');

    const autoScanToggle = document.getElementById('autoScanToggle');
    const countdownText = document.getElementById('countdownText');

    let activeEventSource = null;
    let successfulResults = []; // Persistent across auto-scans

    let autoScanTimer = null;
    let targetTime = 0;

    // Load subnets on start
    fetch('/api/interfaces')
        .then(res => res.json())
        .then(data => {
            subnetSelect.innerHTML = '';
            if (data.subnets && data.subnets.length > 0) {
                data.subnets.forEach(net => {
                    const option = document.createElement('option');
                    option.value = net.subnet;
                    option.textContent = `${net.subnet}.x (${net.ip})`;
                    subnetSelect.appendChild(option);
                });
                scanBtn.disabled = false;
            } else {
                const option = document.createElement('option');
                option.textContent = '未检测到可用局域网接口';
                subnetSelect.appendChild(option);
            }
        })
        .catch(err => {
            console.error('Failed to load interfaces', err);
            subnetSelect.innerHTML = '<option value="">加载网络接口失败</option>';
        });

    const scanIntervalInput = document.getElementById('scanInterval');

    function startTimer() {
        if (!autoScanToggle.checked) return;
        clearInterval(autoScanTimer);
        countdownText.style.display = 'inline';
        
        const mins = parseInt(scanIntervalInput.value, 10) || 5;
        targetTime = Date.now() + mins * 60 * 1000;
        
        autoScanTimer = setInterval(() => {
            const left = Math.round((targetTime - Date.now()) / 1000);
            if (left <= 0) {
                clearInterval(autoScanTimer);
                countdownText.style.display = 'none';
                triggerScan(true); // Trigger auto scan
            } else {
                const m = Math.floor(left / 60).toString().padStart(2, '0');
                const s = (left % 60).toString().padStart(2, '0');
                countdownText.textContent = `(${m}:${s})`;
            }
        }, 1000);
    }

    function stopTimer() {
        clearInterval(autoScanTimer);
        countdownText.style.display = 'none';
    }

    autoScanToggle.addEventListener('change', () => {
        if (autoScanToggle.checked) {
            startTimer();
        } else {
            stopTimer();
        }
    });

    scanBtn.addEventListener('click', () => {
        triggerScan(false);
    });

    function triggerScan(isAuto = false) {
        const subnet = subnetSelect.value;
        if (!subnet) return;

        // Reset UI
        scanBtn.classList.add('loading');
        scanBtn.disabled = true;
        subnetSelect.disabled = true;
        progressContainer.classList.remove('hidden');
        
        if (!isAuto) {
            successfulResults = [];
            resultsBody.innerHTML = '';
            statScanned.textContent = '0';
        }
        
        statTotal.textContent = '-';
        
        progressBar.style.width = '0%';
        progressPercentage.textContent = '0%';
        progressText.textContent = `准备检查 ${subnet}.x ...`;

        if (activeEventSource) {
            activeEventSource.close();
        }

        stopTimer();

        let skipIps = '';
        if (isAuto) {
            // Only skip IPs that already HAVE label studio to prevent checking them again
            skipIps = successfulResults
                .filter(r => r.label_studio_ports.length > 0)
                .map(r => r.ip)
                .join(',');
        }

        let totalIps = 0;
        let completed = 0;

        activeEventSource = new EventSource(`/api/scan?subnet=${encodeURIComponent(subnet)}&skip_ips=${encodeURIComponent(skipIps)}`);

        const skippedCount = (isAuto && skipIps) ? skipIps.split(',').length : 0;

        activeEventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'start') {
                totalIps = data.total;
                statTotal.textContent = totalIps + skippedCount;
                progressText.textContent = `扫描中，并发发起连接...`;
            } 
            else if (data.type === 'progress') {
                completed = data.completed;
                const percent = Math.round((completed / totalIps) * 100);
                
                progressBar.style.width = `${percent}%`;
                progressPercentage.textContent = `${percent}%`;
                
                // Add base completed + already successful from before if auto
                statScanned.textContent = completed + skippedCount;
                
                const res = data.result;
                if (res.open_ports.length > 0) {
                    addOrUpdateResult(res);
                }
            }
            else if (data.type === 'done') {
                finishScan();
            }
        };

        activeEventSource.onerror = () => {
            progressText.textContent = '扫描发生错误或已中断。';
            finishScan();
        };
    }

    function addOrUpdateResult(res) {
        const existingIdx = successfulResults.findIndex(r => r.ip === res.ip);
        if (existingIdx >= 0) {
            res.latest_project = successfulResults[existingIdx].latest_project;
            successfulResults[existingIdx] = res;
        } else {
            successfulResults.push(res);
        }
        
        if (res.label_studio_ports.length > 0 && res.latest_project === undefined) {
            res.latest_project = { loading: true };
            const port = res.label_studio_ports[0];
            const searchVal = document.getElementById('projectSearch').value.trim();
            let apiUrl = `/api/latest_project?ip=${res.ip}&port=${port}`;
            if (searchVal) {
                apiUrl += `&search=${encodeURIComponent(searchVal)}`;
            }
            fetch(apiUrl)
                .then(r => r.json())
                .then(data => {
                    if (data.error) {
                        res.latest_project = { error: data.error };
                    } else if (data.not_found) {
                        res.latest_project = { not_found: true };
                    } else if (data.project) {
                        res.latest_project = { project: data.project };
                    } else {
                        res.latest_project = { project: null };
                    }
                    renderTable();
                })
                .catch(err => {
                    res.latest_project = { error: '网络错误' };
                    renderTable();
                });
        }

        renderTable();
    }

    function renderTable() {
        // Sort: Label Studio passed first, then IP
        successfulResults.sort((a, b) => {
            const aPass = a.label_studio_ports.length > 0 ? 1 : 0;
            const bPass = b.label_studio_ports.length > 0 ? 1 : 0;
            if (aPass !== bPass) return bPass - aPass;
            
            const aNum = a.ip.split('.').map(Number);
            const bNum = b.ip.split('.').map(Number);
            for(let i = 0; i < 4; i++){
                if (aNum[i] !== bNum[i]) return aNum[i] - bNum[i];
            }
            return 0;
        });

        resultsBody.innerHTML = '';
        
        let count8080 = 0;
        let countLS = 0;

        successfulResults.forEach(res => {
            count8080++;
            if (res.label_studio_ports.length > 0) {
                countLS++;
            }
            
            const tr = document.createElement('tr');
            
            // IP
            const tdIp = document.createElement('td');
            tdIp.style.fontWeight = '500';
            tdIp.style.fontFamily = 'monospace';
            tdIp.style.fontSize = '1.05rem';
            tdIp.textContent = res.ip;
            tr.appendChild(tdIp);

            // Open Ports Status
            const td8080 = document.createElement('td');
            const openPortsStr = res.open_ports.join(', ');
            td8080.innerHTML = `<span class="status-badge status-open">${openPortsStr}</span>`;
            tr.appendChild(td8080);
            
            // Label Studio Status
            const tdLS = document.createElement('td');
            if (res.label_studio_ports.length > 0) {
                const lsPortsStr = res.label_studio_ports.join(', ');
                tdLS.innerHTML = `<span class="status-badge status-open pulse">运行在 ${lsPortsStr}</span>`;
            } else {
                tdLS.innerHTML = '<span class="status-badge status-closed">未发现</span>';
            }
            tr.appendChild(tdLS);

            // 项目名称
            const tdProject = document.createElement('td');
            tdProject.style.verticalAlign = 'middle';
            if (res.label_studio_ports.length > 0) {
                if (res.latest_project) {
                    if (res.latest_project.loading) {
                        tdProject.innerHTML = '<div class="loader-spinner" style="width:14px;height:14px;border-width:2px;border-color:var(--text-muted);border-top-color:transparent;display:inline-block;vertical-align:middle;"></div> <span style="font-size:0.85rem;color:var(--text-muted);vertical-align:middle;">检查中...</span>';
                    } else if (res.latest_project.error) {
                        tdProject.innerHTML = `<span style="font-size:0.85rem;color:var(--text-danger);" title="${res.latest_project.error}">获取失败</span>`;
                    } else if (res.latest_project.not_found) {
                        tdProject.innerHTML = '<span style="font-size:0.85rem;color:#f0883e;font-weight:500;">未找到相关项目</span>';
                    } else if (res.latest_project.project) {
                        const proj = res.latest_project.project;
                        const projUrl = `http://${res.ip}:${res.label_studio_ports[0]}/projects/${proj.id}/data`;
                        tdProject.innerHTML = `<a href="${projUrl}" target="_blank" style="color:var(--accent);text-decoration:none;font-weight:500;">${proj.title}</a>`;
                    } else {
                        tdProject.innerHTML = '<span style="font-size:0.85rem;color:var(--text-muted);">暂无项目</span>';
                    }
                } else {
                    tdProject.textContent = '-';
                }
            } else {
                tdProject.textContent = '-';
            }
            tr.appendChild(tdProject);

            // 项目描述
            const tdDesc = document.createElement('td');
            tdDesc.style.fontSize = '0.85rem';
            tdDesc.style.color = 'var(--text-muted)';
            tdDesc.style.maxWidth = '200px';
            tdDesc.style.overflow = 'hidden';
            tdDesc.style.textOverflow = 'ellipsis';
            tdDesc.style.whiteSpace = 'nowrap';
            if (res.label_studio_ports.length > 0 && res.latest_project && res.latest_project.project) {
                const desc = res.latest_project.project.description || '';
                tdDesc.textContent = desc || '-';
                if (desc) tdDesc.title = desc;
            } else {
                tdDesc.textContent = '-';
            }
            tr.appendChild(tdDesc);

            // 更新时间
            const tdTime = document.createElement('td');
            tdTime.style.fontSize = '0.85rem';
            tdTime.style.color = 'var(--text-muted)';
            tdTime.style.whiteSpace = 'nowrap';
            if (res.label_studio_ports.length > 0 && res.latest_project && res.latest_project.project && res.latest_project.project.updated_at) {
                try {
                    const d = new Date(res.latest_project.project.updated_at);
                    tdTime.textContent = d.toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
                } catch(_) {
                    tdTime.textContent = res.latest_project.project.updated_at;
                }
            } else {
                tdTime.textContent = '-';
            }
            tr.appendChild(tdTime);

            resultsBody.appendChild(tr);
        });

        stat8080.textContent = count8080;
        statLabelStudio.textContent = countLS;
    }

    function finishScan() {
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }
        scanBtn.classList.remove('loading');
        scanBtn.disabled = false;
        subnetSelect.disabled = false;
        progressBar.style.width = '100%';
        progressPercentage.textContent = '100%';
        progressText.textContent = '检查完成！';
        
        if (successfulResults.length === 0) {
            resultsBody.innerHTML = '<tr class="empty-row"><td colspan="6">在该网段中未检测到任何开放了探测端口 (8080-8085) 的机器。</td></tr>';
        }

        // Restart loop if enabled
        if (autoScanToggle.checked) {
            startTimer();
        }
    }
});
