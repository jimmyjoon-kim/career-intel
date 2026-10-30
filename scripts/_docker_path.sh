# sourced by the data scripts: find the docker CLI even when it is not on PATH
for d in /Applications/Docker.app/Contents/Resources/bin "$HOME/.docker/bin" /usr/local/bin /opt/homebrew/bin; do
  [ -x "$d/docker" ] && PATH="$d:$PATH"
done
export PATH
