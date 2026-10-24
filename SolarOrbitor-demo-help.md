# Solar Orbitor

Write a program that flies a rocket between planets. This game lets you try the client connection and send actions before the competition. There is no score, fuel, gravity, or collision.

## How to play

### Your rocket

Your team controls one rocket. Each turn, choose a planet or a coordinate to fly toward.

The starter sends the rocket toward Earth. Change its destination to try a different route.

Your rocket starts near the Sun. Choose where it should fly.

[View the game board example](https://lpc.sh/help?rulesVersion=SolarOrbitor-demo#help-start)

### Visit a planet

Choose Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune, or Pluto. Your rocket flies toward that planet at a fixed speed each turn.

When the rocket arrives, it enters orbit. Keep choosing the same planet to stay in orbit. Choose another destination to leave.

The rocket travels to Earth, then follows it in orbit.

**Approaching Earth**

The rocket heads toward Earth.

**Orbiting Earth**

The rocket has reached Earth and entered orbit.

[View the game board example](https://lpc.sh/help?rulesVersion=SolarOrbitor-demo#help-orbit)

### Fly to a coordinate

Choose a point on the map instead of a planet. The rocket flies at the same speed and stops when it reaches that point.

Choosing a coordinate leaves the current orbit. Send a destination each turn to keep the rocket moving. Without an action, it stays still.

The rocket flies to x = 120, y = -80.

**On the way**

The rocket flies toward the chosen point.

**At the destination**

The rocket stops at the chosen point.

[View the game board example](https://lpc.sh/help?rulesVersion=SolarOrbitor-demo#help-movement)

## More about the rules

### Moving targets

Planets move before rockets each turn. A rocket heads toward the new planet position, so its route can change while it travels.

Distances and sizes are stylized.

## Set up your bot

### Start the demo

Log in on the match page and create a practice match while Solar Orbitor is active. Download all the files for your language below, then run the command for your shell.

The client joins your current match. It does not create one. Solar practice advances on the server timer. Run one client per team and restart it for each new match.

One bot session can control each team key in a match. You can still watch in the browser. Custom clients must send the x-bot-session header returned by registration. A disconnected session has 60 seconds to reconnect.

### JavaScript

Install Node.js 22.14 or newer. Check with node --version.

- [solar_template.js](https://lpc.sh/clients/js/solar_template.js): Strategy starter
- [bot_client.js](https://lpc.sh/clients/js/bot_client.js): Connects your strategy to the server
- [package.json](https://lpc.sh/clients/js/solar-package.json): Node package configuration

1. Save solar_template.js, bot_client.js, and package.json in the same folder.
2. Write your strategy in calculateActions in solar_template.js. The example sends your rocket toward Earth.

#### CMD

```
set "API_KEY=your-team-key"
set "LUCID_API_BASE_URL=https://lpc.sh"
npm start
```

#### PowerShell

```
$env:API_KEY = 'your-team-key'
$env:LUCID_API_BASE_URL = 'https://lpc.sh'
npm start
```

#### Bash

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' npm start
```

#### Zsh

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' npm start
```

#### Fish

```
env API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' npm start
```

### Python

Install Python 3.9 or newer. You do not need extra packages.

- [solar_template.py](https://lpc.sh/clients/python/solar_template.py): Strategy starter
- [bot_client.py](https://lpc.sh/clients/python/bot_client.py): Connects your strategy to the server

1. Save solar_template.py and bot_client.py in the same folder.
2. Write your strategy in calculate_actions in solar_template.py. The example sends your rocket toward Earth.

#### CMD

```
set "API_KEY=your-team-key"
set "LUCID_API_BASE_URL=https://lpc.sh"
py -3 solar_template.py
```

#### PowerShell

```
$env:API_KEY = 'your-team-key'
$env:LUCID_API_BASE_URL = 'https://lpc.sh'
py -3 solar_template.py
```

#### Bash

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' python3 solar_template.py
```

#### Zsh

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' python3 solar_template.py
```

#### Fish

```
env API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' python3 solar_template.py
```

### Java

Install JDK 21 or newer and Maven 3.9 or newer. Run java -version and mvn -version. Both must show Java 21 or newer. Maven downloads Gson on the first run.

- [SolarMain.java](https://lpc.sh/clients/java/SolarMain.java): Strategy starter
- [BotClient.java](https://lpc.sh/clients/java/BotClient.java): Connects your strategy to the server
- [pom.xml](https://lpc.sh/clients/java/solar-pom.xml): Maven build configuration

1. Save SolarMain.java, BotClient.java, and pom.xml in one folder.
2. Write your strategy in calculateActions in SolarMain.java. BotClient parses the rocket state into records. The example sends your rocket toward Earth.

#### CMD

```
set "API_KEY=your-team-key"
set "LUCID_API_BASE_URL=https://lpc.sh"
mvn -q compile exec:java
```

#### PowerShell

```
$env:API_KEY = 'your-team-key'
$env:LUCID_API_BASE_URL = 'https://lpc.sh'
mvn -q compile exec:java
```

#### Bash

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' mvn -q compile exec:java
```

#### Zsh

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' mvn -q compile exec:java
```

#### Fish

```
env API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' mvn -q compile exec:java
```

### Rust

Use the current stable release of Rust and Cargo. Cargo downloads packages the first time you run the starter.

- [Cargo.toml](https://lpc.sh/clients/rust/solar.Cargo.toml): Cargo build configuration
- [Cargo.lock](https://lpc.sh/clients/rust/Cargo.lock): Package versions; keep beside Cargo.toml
- [solar.rs](https://lpc.sh/clients/rust/src/solar.rs): Strategy starter; save as src/solar.rs
- [bot_client.rs](https://lpc.sh/clients/rust/src/bot_client.rs): Client helper; save as src/bot_client.rs

1. Save Cargo.toml and Cargo.lock in your client folder. Save solar.rs and bot_client.rs in a src subfolder.
2. Write your strategy in calculate_actions in src/solar.rs. BotClient parses the rocket state into structs. The example sends your rocket toward Earth.

#### CMD

```
set "API_KEY=your-team-key"
set "LUCID_API_BASE_URL=https://lpc.sh"
cargo run --release
```

#### PowerShell

```
$env:API_KEY = 'your-team-key'
$env:LUCID_API_BASE_URL = 'https://lpc.sh'
cargo run --release
```

#### Bash

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' cargo run --release
```

#### Zsh

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' cargo run --release
```

#### Fish

```
env API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' cargo run --release
```

### C++

Install a C++20 compiler, CMake 3.20+, and libcurl development files with HTTPS support. On Ubuntu: sudo apt install g++ cmake libcurl4-openssl-dev. On macOS: install Xcode command-line tools and brew install cmake curl. On Windows: use Visual Studio C++ tools and vcpkg install curl, then pass its CMake toolchain file when configuring. CMake downloads nlohmann/json if it is not installed.

- [solar_template.cpp](https://lpc.sh/clients/cpp/solar_template.cpp): Strategy starter
- [bot_client.hpp](https://lpc.sh/clients/cpp/bot_client.hpp): Connects your strategy to the server
- [CMakeLists.txt](https://lpc.sh/clients/cpp/CMakeLists.txt): CMake build configuration

1. Save all three files in one folder. Configure with cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DLPC_STRATEGY=solar_template.cpp, then build with cmake --build build --config Release. Rebuild after editing your strategy.
2. Write calculate_actions in solar_template.cpp. The example sends your rocket toward Earth.

#### CMD

```
set "API_KEY=your-team-key"
set "LUCID_API_BASE_URL=https://lpc.sh"
.\build\bin\lpc-bot.exe
```

#### PowerShell

```
$env:API_KEY = 'your-team-key'
$env:LUCID_API_BASE_URL = 'https://lpc.sh'
.\build\bin\lpc-bot.exe
```

#### Bash

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' ./build/bin/lpc-bot
```

#### Zsh

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' ./build/bin/lpc-bot
```

#### Fish

```
env API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' ./build/bin/lpc-bot
```

### Go

Install Go 1.22 or newer. No external packages are needed.

- [solar_template.go](https://lpc.sh/clients/go/solar_template.go): Strategy starter
- [bot_client.go](https://lpc.sh/clients/go/bot_client.go): Connects your strategy to the server
- [go.mod](https://lpc.sh/clients/go/go.mod): Go module configuration

1. Save solar_template.go, bot_client.go, and go.mod in one folder.
2. Write calculateActions in solar_template.go. The example sends your rocket toward Earth.

#### CMD

```
set "API_KEY=your-team-key"
set "LUCID_API_BASE_URL=https://lpc.sh"
go run solar_template.go bot_client.go
```

#### PowerShell

```
$env:API_KEY = 'your-team-key'
$env:LUCID_API_BASE_URL = 'https://lpc.sh'
go run solar_template.go bot_client.go
```

#### Bash

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' go run solar_template.go bot_client.go
```

#### Zsh

```
API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' go run solar_template.go bot_client.go
```

#### Fish

```
env API_KEY='your-team-key' LUCID_API_BASE_URL='https://lpc.sh' go run solar_template.go bot_client.go
```

## API and reference

### Rocket action format

Use the rocket ID in view.entityId as the action key. A planet action uses its name, such as { "type": "Earth" }. Planet names are case-sensitive.

A coordinate action looks like { "type": "move", "x": 120, "y": -80 }. Each rocket takes one action per turn. The starter code shows where to return it.

Use the authenticated team identity to identify your team. Keep the key private. If the client stops, check the error and your match before restarting.

## Full rules

Write a program that flies a rocket between planets. This game lets you try the client connection and send actions before the competition. There is no score, fuel, gravity, or collision.

## Your rocket

Your team controls one rocket. Each turn, choose a planet or a coordinate to fly toward.

The starter sends the rocket toward Earth. Change its destination to try a different route.

## Visit a planet

Choose Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune, or Pluto. Your rocket flies toward that planet at a fixed speed each turn.

When the rocket arrives, it enters orbit. Keep choosing the same planet to stay in orbit. Choose another destination to leave.

## Fly to a coordinate

Choose a point on the map instead of a planet. The rocket flies at the same speed and stops when it reaches that point.

Choosing a coordinate leaves the current orbit. Send a destination each turn to keep the rocket moving. Without an action, it stays still.

## Moving targets

Planets move before rockets each turn. A rocket heads toward the new planet position, so its route can change while it travels.

Distances and sizes are stylized.

## Start the demo

Log in on the match page and create a practice match while Solar Orbitor is active. Download all the files for your language below, then run the command for your shell.

The client joins your current match. It does not create one. Solar practice advances on the server timer. Run one client per team and restart it for each new match.

One bot session can control each team key in a match. You can still watch in the browser. Custom clients must send the x-bot-session header returned by registration. A disconnected session has 60 seconds to reconnect.

## Rocket action format

Use the rocket ID in view.entityId as the action key. A planet action uses its name, such as { "type": "Earth" }. Planet names are case-sensitive.

A coordinate action looks like { "type": "move", "x": 120, "y": -80 }. Each rocket takes one action per turn. The starter code shows where to return it.

Use the authenticated team identity to identify your team. Keep the key private. If the client stops, check the error and your match before restarting.
