"""User domain: consultation, creation, modification, lifecycle and deletion.

Layer rule: `ldap3`, `subprocess` and `os.chown` are not imported here. Everything that
touches the outside world goes through the ports in `core/ports.py`, injected in an
`Environment`. That is the reason this package can be tested whole, with no cluster.
"""
