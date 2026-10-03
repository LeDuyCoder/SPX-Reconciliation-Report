import { useState } from 'react';
import {
  ArrowDown, ArrowRight, ArrowUpRight, Boxes, Check, ChevronDown,
  CircleHelp, Database, FilePenLine, FileSpreadsheet, Filter, HardDrive,
  Mail, Menu, Search, ShieldCheck, Sparkles, X,
} from 'lucide-react';

const downloadUrl = (import.meta.env.VITE_DOWNLOAD_URL || '').trim();

function Brand({ light = false }) {
  return (
    <a className={`brand ${light ? 'brand-light' : ''}`} href="#top" aria-label="SPX Reconciliation Report">
      <img src="/logo.png" alt="" />
      <span className="brand-copy"><b>SPX<span>R</span></b><small>RECONCILIATION REPORT</small></span>
    </a>
  );
}

function DownloadLink({ children, className = '' }) {
  return downloadUrl ? (
    <a className={className} href={downloadUrl} download="SPXReconciliationReport.exe">
      {children}
    </a>
  ) : (
    <a className={className} href="#download">{children}</a>
  );
}

function ProductPreview() {
  return (
    <div className="preview-wrap" aria-label="Minh họa màn hình quản lý workspace trong ứng dụng">
      <div className="preview-orbit orbit-one" /><div className="preview-orbit orbit-two" />
      <div className="app-window">
        <aside className="app-sidebar">
          <div className="app-brand"><img src="/logo.png" alt="" /><span className="app-brand-copy"><b>SPX</b><small>RECONCILIATION</small></span></div>
          <div className="sidebar-caption">WORKSPACE</div>
          <div className="side-item active"><Boxes size={15} /> Workspaces</div>
          <div className="side-item"><FileSpreadsheet size={15} /> Dữ liệu chính</div>
          <div className="side-item"><Mail size={15} /> Gửi Email</div>
          <div className="side-item"><FilePenLine size={15} /> Email Template</div>
          <button className="sidebar-create"><span>＋</span> Tạo workspace</button>
          <div className="sidebar-bottom"><span>Chưa chọn workspace</span><small><i className="online-dot" /> Lưu trữ cục bộ · SQLite</small></div>
        </aside>
        <div className="app-main workspace-screen">
          <div className="app-topline"><div><span className="crumb">SPX　/</span> Workspaces</div><div className="ready-status"><i /> Sẵn sàng</div></div>
          <div className="workspace-title-row">
            <div><p className="app-eyebrow">QUẢN LÝ DỮ LIỆU ĐỐI SOÁT</p><h3>Workspaces</h3><p className="workspace-summary">1 workspace · 7,752 bản ghi trên thiết bị này</p></div>
            <button className="workspace-create"><span>＋</span> Tạo workspace</button>
          </div>
          <div className="workspace-list-heading"><b>DANH SÁCH WORKSPACE</b><span>1 workspace</span></div>
          <article className="workspace-card">
            <div className="workspace-logo">SPX</div>
            <div className="workspace-info">
              <div className="workspace-name-line"><h4>Báo cáo tháng 10</h4><span className="workspace-count">7,752 bản ghi</span></div>
              <p className="workspace-description">Đối soát SPX · Demo</p>
              <div className="workspace-meta"><span><FileSpreadsheet size={11} /> Thu Dau Mot Hub.xlsx</span><i /> <span>Nhập lúc 03/10/2026 02:49</span></div>
            </div>
            <div className="workspace-actions"><button className="open-workspace">Mở workspace</button><button className="rename-workspace">Đổi tên</button><button className="delete-workspace">Xóa</button></div>
          </article>
          <div className="workspace-empty"><span>＋</span><b>Tạo workspace mới</b><small>Mỗi báo cáo, một không gian làm việc riêng.</small></div>
        </div>
      </div>
      <div className="float-card float-import"><span className="float-icon"><Boxes size={16} /></span><span><b>Workspace sẵn sàng</b><small>7,752 bản ghi đang quản lý</small></span><Check size={15} className="float-check" /></div>
      <div className="float-card float-email"><span className="float-icon mail-icon"><FileSpreadsheet size={16} /></span><span><b>File Excel gần nhất</b><small>Thu Dau Mot Hub.xlsx</small></span></div>
    </div>
  );
}
const features = [
  { icon: FileSpreadsheet, title: 'Nhập Excel nhanh', text: 'Xem trước dữ liệu, chọn sheet Main Data và nhập hàng nghìn dòng theo lô.' },
  { icon: Search, title: 'Tìm và lọc linh hoạt', text: 'Tìm theo mã vận đơn, chuyến hoặc trạm. Lọc và sắp xếp trực tiếp trên dữ liệu.' },
  { icon: Mail, title: 'Gửi báo cáo tiện lợi', text: 'Tạo email template, xem trước nội dung và gửi file Excel qua Gmail OAuth.' },
  { icon: HardDrive, title: 'Lưu trữ trên máy', text: 'Workspace và dữ liệu được lưu trong SQLite cục bộ trên máy tính Windows.' },
];

const steps = [
  ['01', 'Tạo workspace', 'Tạo không gian làm việc riêng cho từng báo cáo hoặc đợt đối soát.'],
  ['02', 'Nhập file Excel', 'Chọn workbook có sheet Main Data và kiểm tra dữ liệu trước khi nhập.'],
  ['03', 'Đối soát & gửi', 'Tìm, lọc, chọn bản ghi rồi xuất Excel và gửi báo cáo qua email.'],
];

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);
  return (
    <div id="top">
      <header className="site-header">
        <div className="nav-shell"><Brand />
          <nav className={menuOpen ? 'nav-links open' : 'nav-links'}>
            <a href="#features" onClick={closeMenu}>Tính năng</a><a href="#workflow" onClick={closeMenu}>Cách hoạt động</a><a href="#download" onClick={closeMenu}>Tải ứng dụng</a>
          </nav>
          <DownloadLink className="nav-download">Tải ứng dụng <ArrowDown size={15} /></DownloadLink>
          <button className="menu-toggle" onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? 'Đóng menu' : 'Mở menu'}>{menuOpen ? <X /> : <Menu />}</button>
        </div>
      </header>

      <main>
        <section className="hero section-shell">
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-dot" /> CÔNG CỤ ĐỐI SOÁT CHO SPX</div>
            <h1>Đối soát dữ liệu.<br /><em>Nhẹ nhàng hơn.</em></h1>
            <p className="hero-description">Quản lý dữ liệu SPX từ Excel, theo dõi TO và Order, rồi gửi báo cáo trong một ứng dụng desktop gọn gàng.</p>
            <div className="hero-actions"><DownloadLink className="button-primary">Tải ứng dụng Windows <ArrowDown size={17} /></DownloadLink><a className="button-secondary" href="#features">Khám phá tính năng <ArrowRight size={16} /></a></div>
            <div className="hero-meta"><span><ShieldCheck size={15} /> Dữ liệu lưu cục bộ</span><span className="meta-divider" /><span>Windows desktop</span></div>
          </div>
          <ProductPreview />
          <div className="hero-note"><Sparkles size={14} /> Từ file Excel đến báo cáo sẵn sàng gửi</div>
        </section>

        <section className="trust-strip"><div className="section-shell trust-inner"><span>THIẾT KẾ CHO QUY TRÌNH ĐỐI SOÁT HẰNG NGÀY</span><div><span><Database size={16} /> SQLite cục bộ</span><span><FileSpreadsheet size={16} /> Excel</span><span><Mail size={16} /> Gmail OAuth</span></div></div></section>

        <section className="features-section section-shell" id="features">
          <div className="section-heading"><div className="eyebrow">MỌI THỨ Ở ĐÚNG CHỖ</div><h2>Tập trung vào việc đối soát,<br /><em>không phải xử lý thủ công.</em></h2><p>Các công cụ cần thiết cho một quy trình rõ ràng, từ dữ liệu đầu vào đến báo cáo gửi đi.</p></div>
          <div className="feature-grid">{features.map(({ icon: Icon, title, text }, index) => <article className="feature-card" key={title}><div className="feature-top"><span className="feature-icon"><Icon size={19} /></span><span className="feature-index">0{index + 1}</span></div><h3>{title}</h3><p>{text}</p><ArrowUpRight className="feature-arrow" size={17} /></article>)}</div>
        </section>

        <section className="workflow-section" id="workflow"><div className="section-shell workflow-inner"><div className="workflow-copy"><div className="eyebrow">BA BƯỚC ĐƠN GIẢN</div><h2>Từ dữ liệu thô<br /><em>đến báo cáo rõ ràng.</em></h2><p>SPX Reconciliation Report gom các bước rời rạc vào một nơi để bạn theo dõi toàn bộ tiến trình.</p><a href="#download" className="text-link">Bắt đầu sử dụng <ArrowRight size={16} /></a></div><div className="steps-list">{steps.map(([number, title, text]) => <article className="step" key={number}><div className="step-number">{number}</div><div><h3>{title}</h3><p>{text}</p></div><ChevronDown size={17} className="step-mark" /></article>)}</div></div></section>

        <section className="download-section section-shell" id="download"><div className="download-card"><div className="download-art"><div className="art-ring ring-a"/><div className="art-ring ring-b"/><div className="download-app-icon"><img src="/logo.png" alt="SPX Reconciliation Report" /></div><span className="art-chip chip-one"><FileSpreadsheet size={15} /> XLSX</span><span className="art-chip chip-two"><Check size={15} /> Ready</span></div><div className="download-copy"><div className="eyebrow">SẴN SÀNG BẮT ĐẦU?</div><h2>Mang quy trình<br /><em>đối soát về desktop.</em></h2><p>Tải ứng dụng Windows, tạo workspace đầu tiên và bắt đầu với file Excel của bạn.</p>{downloadUrl ? <DownloadLink className="button-primary">Tải SPX Reconciliation Report <ArrowDown size={17} /></DownloadLink> : <div className="download-pending"><CircleHelp size={17} /><span>Bản cài đặt Windows đang được cập nhật. Vui lòng quay lại sau.</span></div>}<small className="download-caption">Ứng dụng desktop cho Windows · Dữ liệu được lưu cục bộ</small></div></div></section>
      </main>

      <footer className="site-footer"><div className="section-shell footer-inner"><Brand light /><div className="footer-copy"><span>SPX Reconciliation Report</span><span>Đối soát dữ liệu rõ ràng, gửi báo cáo gọn gàng.</span></div><a href="#top" className="back-top">Lên đầu trang ↑</a><small>© {new Date().getFullYear()} DuyJKR Studio</small></div></footer>
    </div>
  );
}

export default App;
