use std::process::{Command, Child};
use std::sync::Mutex;
use std::net::TcpStream;
use std::time::Duration;
use tauri::Manager;

/// Dedicated port for the embedded Redis server to avoid conflicts with user-local Redis.
const REDIS_PORT: u16 = 16379;

struct AppState {
    backend_process: Mutex<Option<Child>>,
    redis_process: Mutex<Option<Child>>,
}

fn find_free_port(start: u16, end: u16) -> Option<u16> {
    for port in start..=end {
        if TcpStream::connect_timeout(&format!("127.0.0.1:{}", port).parse().unwrap(), Duration::from_millis(50)).is_err() {
            return Some(port);
        }
    }
    None
}

fn wait_for_redis(port: u16, timeout_secs: u64) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed().as_secs() < timeout_secs {
        if TcpStream::connect_timeout(&format!("127.0.0.1:{}", port).parse().unwrap(), Duration::from_millis(100)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

fn wait_for_backend(port: u16, timeout_secs: u64) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed().as_secs() < timeout_secs {
        if TcpStream::connect_timeout(&format!("127.0.0.1:{}", port).parse().unwrap(), Duration::from_millis(100)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

fn start_redis() -> Option<Child> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let redis_path = exe_dir.join("redis-server");
    if !redis_path.exists() {
        eprintln!("Warning: redis-server binary not found at {:?}", redis_path);
        return None;
    }
    let temp_dir = std::env::temp_dir().join("agent-factory-redis");
    std::fs::create_dir_all(&temp_dir).ok()?;
    match Command::new(&redis_path)
        .args(&["--port", &REDIS_PORT.to_string(), "--dir", &temp_dir.to_string_lossy(), "--daemonize", "no"])
        .spawn() {
        Ok(child) => {
            println!("Started embedded redis-server on port {}", REDIS_PORT);
            Some(child)
        }
        Err(e) => {
            eprintln!("Warning: failed to start redis-server: {}", e);
            None
        }
    }
}

fn start_backend(port: u16, redis_port: u16) -> Option<Child> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let backend_path = exe_dir.join("agent-factory-backend");
    if !backend_path.exists() {
        eprintln!("Error: agent-factory-backend not found at {:?}", backend_path);
        return None;
    }
    let data_dir = dirs::data_dir()?.join("Agent Factory");
    std::fs::create_dir_all(&data_dir).ok()?;
    match Command::new(&backend_path)
        .args(&["--port", &port.to_string(), "--data-dir", &data_dir.to_string_lossy(), "--no-feishu"])
        .env("ENV", "production")
        .env("REDIS_PORT", &redis_port.to_string())
        .spawn() {
        Ok(child) => {
            println!("Started backend on port {}", port);
            Some(child)
        }
        Err(e) => {
            eprintln!("Error: failed to start backend: {}", e);
            None
        }
    }
}

fn main() {
    let port = find_free_port(18000, 18100).expect("No free port found");

    let redis_process = start_redis();
    println!("Waiting for Redis to be ready...");
    if !wait_for_redis(REDIS_PORT, 10) {
        eprintln!("Redis failed to start within 10 seconds");
        std::process::exit(1);
    }
    println!("Redis ready at localhost:{}", REDIS_PORT);

    let backend_process = start_backend(port, REDIS_PORT).expect("Failed to start backend");

    println!("Waiting for backend to be ready...");
    if !wait_for_backend(port, 30) {
        eprintln!("Backend failed to start within 30 seconds");
        std::process::exit(1);
    }
    println!("Backend ready at http://localhost:{}", port);

    let backend_port = port;

    tauri::Builder::default()
        .manage(AppState {
            backend_process: Mutex::new(Some(backend_process)),
            redis_process: Mutex::new(redis_process),
        })
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(move |app| {
            let url = format!("http://localhost:{}", backend_port);
            let _window = tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::External(url.parse().unwrap())
            )
            .title("Agent Factory")
            .inner_size(1400.0, 900.0)
            .center()
            .build()?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // 优雅关闭子进程
                if let Some(state) = window.app_handle().try_state::<AppState>() {
                    if let Ok(mut child) = state.backend_process.lock() {
                        if let Some(mut c) = child.take() {
                            let _ = c.kill();
                        }
                    }
                    if let Ok(mut child) = state.redis_process.lock() {
                        if let Some(mut c) = child.take() {
                            let _ = c.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
