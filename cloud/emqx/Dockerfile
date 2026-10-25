# EMQX with the MedMusketeer configuration baked in (no bind mount); secrets are rendered into
# etc/emqx.conf at start by mm-entrypoint.sh. The cloud certificate comes from the emqx-certs volume.
FROM emqx/emqx:6.3.2
COPY --chown=emqx:emqx emqx.conf.template /opt/emqx/etc/emqx.conf.template
COPY --chmod=755 mm-entrypoint.sh /usr/local/bin/mm-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/mm-entrypoint.sh"]
CMD ["/opt/emqx/bin/emqx", "foreground"]
