// tests/adapters/ip_delayer.cpp
// Cross-platform UDP+TCP "delayer" server.

#include <chrono>
#include <thread>
#include <string>
#include <vector>
#include <atomic>
#include <mutex>
#include <iostream>
#include <sstream>
#include <algorithm>
#include <cctype>
#include <memory>  // <-- needed for shared_ptr/make_shared

#if defined(_WIN32)
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")
  using socklen_t = int;
  static bool wsa_inited = false;
  static void winsock_init() {
      if (!wsa_inited) { WSADATA wsa; WSAStartup(MAKEWORD(2,2), &wsa); wsa_inited = true; }
  }
  static void closesock(SOCKET s){ closesocket(s); }
  using socket_t = SOCKET;
#else
  #include <sys/types.h>
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <netdb.h>
  #include <unistd.h>
  using socket_t = int;
  static void closesock(int s){ close(s); }
  static void winsock_init() {}
#endif

using Steady = std::chrono::steady_clock;
using namespace std::chrono;

static std::string trim(const std::string& s) {
    auto b = s.begin(), e = s.end();
    while (b != e && std::isspace(static_cast<unsigned char>(*b))) ++b;
    while (e != b && std::isspace(static_cast<unsigned char>(*(e-1)))) --e;
    return std::string(b,e);
}

static std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> out;
    std::string cur;
    std::stringstream ss(s);
    while (std::getline(ss, cur, delim)) out.push_back(cur);
    return out;
}

struct SendJobTCP {
    std::shared_ptr<std::mutex> wmutex;
    socket_t sock;
    std::string data;
    double delay_s;
};

struct SendJobUDP {
    socket_t sock;
    sockaddr_storage addr{};
    socklen_t addrlen{};
    std::string data;
    double delay_s;
};

static void sleep_until_steady(Steady::time_point tp) {
    using namespace std::chrono;
    for (;;) {
        auto now = Steady::now();
        if (now >= tp) break;
        auto remaining = tp - now;
        if (remaining > microseconds(500)) std::this_thread::sleep_for(remaining - microseconds(200));
        else { /* busy */ }
    }
}

static void schedule_tcp_echo(SendJobTCP job) {
    std::cout << "TCP Echo" << std::endl;
    auto delta = duration<double>(job.delay_s);
    auto tp = Steady::now() + duration_cast<Steady::duration>(delta);
    sleep_until_steady(tp);
    std::lock_guard<std::mutex> lk(*job.wmutex);
#if defined(_WIN32)
    send(job.sock, job.data.c_str(), static_cast<int>(job.data.size()), 0);
#else
    ::send(job.sock, job.data.c_str(), job.data.size(), 0);
#endif
}

static void schedule_udp_echo(SendJobUDP job) {
    std::cout << "UDP Echo" << std::endl;
    auto delta = duration<double>(job.delay_s);
    auto tp = Steady::now() + duration_cast<Steady::duration>(delta);
    sleep_until_steady(tp);
#if defined(_WIN32)
    sendto(job.sock, job.data.c_str(), static_cast<int>(job.data.size()), 0,
           reinterpret_cast<const sockaddr*>(&job.addr), job.addrlen);
#else
    ::sendto(job.sock, job.data.c_str(), job.data.size(), 0,
             reinterpret_cast<const sockaddr*>(&job.addr), job.addrlen);
#endif
}

static bool parse_payload(const std::string& payload, std::vector<std::pair<std::string,double>>& out_pairs) {
    out_pairs.clear();
    auto seqs = split(payload, ';'); // every sequence now ends with ';'
    for (auto& s : seqs) {
        //s = trim(s);
        if (s.empty()) continue;  // skip the empty entry from the final ';'
        auto parts = split(s, ',');
        if (parts.size() != 2) return false;
        auto data = parts[0];
        try {
            //double d = std::stod(trim(parts[1]));
            double d = std::stod(parts[1]);
            if (d < 0) d = 0;
            out_pairs.emplace_back(std::move(data), d);
        } catch (...) {
            return false;
        }
    }
    return !out_pairs.empty();
}

static void tcp_client_thread(socket_t csock) {
    auto wmutex = std::make_shared<std::mutex>(); // per-connection write lock
    std::string buffer;
    buffer.reserve(4096);
    char buf[4096];

    for (;;) {
#if defined(_WIN32)
        int n = recv(csock, buf, sizeof(buf), 0);
#else
        int n = ::recv(csock, buf, sizeof(buf), 0);
#endif
        if (n <= 0) break;
        buffer.append(buf, buf + n);

        // process complete payloads ending with ';'
        size_t pos;
        while ((pos = buffer.find(';')) != std::string::npos) {
            // include the ';' in the extracted part
            std::string chunk = buffer.substr(0, pos + 1);
            buffer.erase(0, pos + 1);

            std::vector<std::pair<std::string,double>> pairs;
            if (!parse_payload(chunk, pairs)) {
                const char* err = "ERR;";
#if defined(_WIN32)
                send(csock, err, 4, 0);
#else
                ::send(csock, err, 4, 0);
#endif
                continue;
            }
            for (auto& pd : pairs) {
                // TCP echo will also end each reply with ';'
                SendJobTCP job{wmutex, csock, pd.first, pd.second};
                std::thread(schedule_tcp_echo, job).detach();
            }
        }
    }
    std::cout << "Closing socket (tcp client thread)" << std::endl;
    closesock(csock);
}


static void tcp_server_thread(uint16_t port) {
    socket_t lsock = ::socket(AF_INET, SOCK_STREAM, 0);
    if (lsock < 0) { std::cerr << "TCP socket failed\n"; return; }

    int yes = 1;
#if defined(_WIN32)
    setsockopt(lsock, SOL_SOCKET, SO_REUSEADDR, (const char*)&yes, sizeof(yes));
#else
    setsockopt(lsock, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
#endif

    sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_addr.s_addr = htonl(INADDR_ANY); addr.sin_port = htons(port);
    if (bind(lsock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        std::cout << "Closing socket (tcp bind fail)" << std::endl;
        std::cerr << "TCP bind failed (port busy?)\n";
        closesock(lsock);
        return;
    }
    if (listen(lsock, 16) != 0) {
        std::cout << "Closing socket (tcp listen fail)" << std::endl;
        std::cerr << "listen failed\n";
        closesock(lsock);
        return;
    }

    for (;;) {
        sockaddr_in caddr{}; socklen_t clen = sizeof(caddr);
        socket_t csock = accept(lsock, reinterpret_cast<sockaddr*>(&caddr), &clen);
        if (csock < 0) break;
        std::thread(tcp_client_thread, csock).detach();
    }
    std::cout << "Closing socket (tcp server thread)" << std::endl;
    closesock(lsock);
}

static void udp_server_thread(uint16_t port) {
    socket_t usock = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (usock < 0) { std::cerr << "UDP socket failed\n"; return; }

    int yes = 1;
#if defined(_WIN32)
    setsockopt(usock, SOL_SOCKET, SO_REUSEADDR, (const char*)&yes, sizeof(yes));
#else
    setsockopt(usock, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
#endif

    sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_addr.s_addr = htonl(INADDR_ANY); addr.sin_port = htons(port);
    if (bind(usock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        std::cout << "Closing socket (udp fail)" << std::endl;
        std::cerr << "UDP bind failed (port busy?)\n";
        closesock(usock);
        return;
    }

    for (;;) {
        char buf[65536];
        sockaddr_storage src{}; socklen_t slen = sizeof(src);
#if defined(_WIN32)
        int n = recvfrom(usock, buf, sizeof(buf), 0, reinterpret_cast<sockaddr*>(&src), &slen);
#else
        int n = ::recvfrom(usock, buf, sizeof(buf), 0, reinterpret_cast<sockaddr*>(&src), &slen);
#endif
        if (n <= 0) continue;
        std::string payload(buf, buf + n);
        //payload = trim(payload);
        std::vector<std::pair<std::string,double>> pairs;
        if (!parse_payload(payload, pairs)) {
            static const char err[] = "ERR";
#if defined(_WIN32)
            sendto(usock, err, 3, 0, reinterpret_cast<sockaddr*>(&src), slen);
#else
            ::sendto(usock, err, 3, 0, reinterpret_cast<sockaddr*>(&src), slen);
#endif
            continue;
        }
        for (auto& pd : pairs) {
            SendJobUDP job{usock, src, slen, pd.first, pd.second};
            std::thread(schedule_udp_echo, job).detach();
        }
    }
    // keep socket open while thread runs
}

int main(int argc, char** argv) {
    winsock_init();
    uint16_t port = 5000;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if ((a == "--port" || a == "-p") && i + 1 < argc) {
            port = static_cast<uint16_t>(std::stoi(argv[++i]));
        } else if (a == "--help" || a == "-h") {
            std::cout << "Usage: " << argv[0] << " [--port N]\n";
            return 0;
        }
    }
    std::thread udp(udp_server_thread, port);
    std::thread tcp(tcp_server_thread, port);
    std::cout << "delayer listening on UDP/TCP port " << port << std::endl;
    udp.join(); tcp.join();
    return 0;
}
