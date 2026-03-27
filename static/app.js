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
        progressText.textContent = `准备扫描 ${subnet}.x ...`;

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

        activeEventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'start') {
                totalIps = data.total;
                statTotal.textContent = totalIps + (isAuto ? successfulResults.length : 0);
                progressText.textContent = `扫描中，并发发起连接...`;
            } 
            else if (data.type === 'progress') {
                completed = data.completed;
                const percent = Math.round((completed / totalIps) * 100);
                
                progressBar.style.width = `${percent}%`;
                progressPercentage.textContent = `${percent}%`;
                
                // Add base completed + already successful from before if auto
                statScanned.textContent = completed + (isAuto && skipIps ? skipIps.split(',').length : 0);
                
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
            successfulResults[existingIdx] = res;
        } else {
            successfulResults.push(res);
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

            // Actions
            const tdAction = document.createElement('td');
            if (res.label_studio_ports.length > 0) {
                const a = document.createElement('a');
                a.href = `http://${res.ip}:${res.label_studio_ports[0]}/`;
                a.target = '_blank';
                a.className = 'link-btn';
                a.innerHTML = '直达应用 ↗';
                tdAction.appendChild(a);
            } else {
                const a = document.createElement('a');
                a.href = `http://${res.ip}:${res.open_ports[0]}/`;
                a.target = '_blank';
                a.className = 'link-btn';
                a.style.color = 'var(--text-muted)';
                a.innerHTML = `查看端口 ${res.open_ports[0]} ↗`;
                tdAction.appendChild(a);
            }
            tr.appendChild(tdAction);

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
        progressText.textContent = '扫描完成！';
        
        if (successfulResults.length === 0) {
            resultsBody.innerHTML = '<tr class="empty-row"><td colspan="4">在该网段中未检测到任何开放了探测端口 (8080-8085) 的机器。</td></tr>';
        }

        // Restart loop if enabled
        if (autoScanToggle.checked) {
            startTimer();
        }
    }
});
