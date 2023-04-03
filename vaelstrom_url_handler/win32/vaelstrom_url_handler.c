#include <winsock2.h>
#include <ws2tcpip.h>

// note that this is ignored with /NODEFAULTLIB and needs to be passed to the linker explicitly in that case
#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "Shell32.lib")

#define DEFAULT_PORT "58238"
#define DEFAULT_BUFLEN 1024
#define PYTHON_LENGTH_FIELD_SIZE 4

#ifdef DEBUG
#include <stdio.h>
#else
#define printf(fmt, ...) (0)
#endif

// send first command line parameter to a local address
// then quit
// most of this is copied from windows api docs

int wmain(int argc, wchar_t **argv) {
  if (argc <= 1) {
    printf("No argument given.\n");
    return 1;
  }
  size_t url_length = wcslen(argv[1]);
  size_t url_length_bytes = url_length * sizeof(wchar_t);
  if (url_length_bytes > DEFAULT_BUFLEN * sizeof(wchar_t) - PYTHON_LENGTH_FIELD_SIZE)
  {
    printf("Argument too long.\n");
    return 1;
  }

  WSADATA wsaData;
  int iResult;
  // Initialize Winsock
  iResult = WSAStartup(MAKEWORD(2,2), &wsaData);
  if (iResult != 0) {
    printf("WSAStartup failed: %d\n", iResult);
    return 1;
  }

  // create client socket
  struct addrinfo *result = NULL,
                  *ptr = NULL,
                  hints;

  ZeroMemory( &hints, sizeof(hints) );
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_protocol = IPPROTO_TCP;

  // Resolve the server address and port
  iResult = getaddrinfo("127.0.0.1", DEFAULT_PORT, &hints, &result);
  if (iResult != 0) {
    printf("getaddrinfo failed: %d\n", iResult);
    WSACleanup();
    return 1;
  }

  SOCKET ConnectSocket = INVALID_SOCKET;

  // Attempt to connect to the first address returned by
  // the call to getaddrinfo
  ptr = result;

  // Create a SOCKET for connecting to server
  ConnectSocket = socket(ptr->ai_family, ptr->ai_socktype, 
    ptr->ai_protocol);

  // Check for errors to ensure that the socket is a valid socket.
  if (ConnectSocket == INVALID_SOCKET) {
    printf("Error at socket(): %ld\n", WSAGetLastError());
    freeaddrinfo(result);
    WSACleanup();
    return 1;
  }

  // Connect to server.
  iResult = connect( ConnectSocket, ptr->ai_addr, (int)ptr->ai_addrlen);
  if (iResult == SOCKET_ERROR) {
    closesocket(ConnectSocket);
    ConnectSocket = INVALID_SOCKET;
  }

  // Should really try the next address returned by getaddrinfo
  // if the connect call failed
  // But for this simple example we just free the resources
  // returned by getaddrinfo and print an error message

  freeaddrinfo(result);

  if (ConnectSocket == INVALID_SOCKET) {
    printf("Unable to connect to server!\n");
    WSACleanup();
    return 1;
  }

  // send first arg
  // prefix with its length as a 4 byte field
  wchar_t sendbuf[DEFAULT_BUFLEN];
  size_t val = htonl(url_length_bytes);
  memcpy((char*)sendbuf, &val, PYTHON_LENGTH_FIELD_SIZE);
  memcpy((char*)sendbuf + PYTHON_LENGTH_FIELD_SIZE, argv[1], url_length_bytes);
  printf("sending: %ls\n", argv[1]);

  iResult = send(ConnectSocket, (char*)sendbuf, url_length_bytes + PYTHON_LENGTH_FIELD_SIZE, 0);
  if (iResult == SOCKET_ERROR) {
      printf("send failed: %d\n", WSAGetLastError());
      closesocket(ConnectSocket);
      WSACleanup();
      return 1;
  }
  printf("Bytes Sent: %ld\n", iResult);

  // close connection
  iResult = shutdown(ConnectSocket, SD_BOTH);
  if (iResult == SOCKET_ERROR) {
      printf("shutdown failed: %d\n", WSAGetLastError());
      closesocket(ConnectSocket);
      WSACleanup();
      return 1;
  }

  // clean up socket resources
  closesocket(ConnectSocket);
  WSACleanup();

  return 0;
}

// entry point for /SUBSYSTEM:WINDOWS with /NODEFAULTLIB
int __stdcall WinMainCRTStartup()
{
  // int Result = WinMain(GetModuleHandle(0), 0, 0, 0);
  // return Result;
  int argc;
  LPWSTR* args = CommandLineToArgvW(GetCommandLineW(), &argc);
  return wmain(argc, args);
}

// entry point for /SUBSYSTEM:WINDOWS without /NODEFAULTLIB
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPTSTR lpCmdLine, int nShowCmd) {
  (void)hInstance;
  (void)hPrevInstance;
  (void)lpCmdLine;
  (void)nShowCmd;
  return WinMainCRTStartup();
}

#pragma function(memcpy)
void *memcpy(void *dest, const void *src, size_t count)
{
  char *dest8 = (char *)dest;
  const char *src8 = (const char *)src;
  while (count--)
  {
    *dest8++ = *src8++;
  }
  return dest;
}
