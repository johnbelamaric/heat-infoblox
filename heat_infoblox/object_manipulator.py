# Copyright 2015 Infoblox Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import gettext
import logging

from heat_infoblox import ibexceptions as exc

_ = gettext.gettext

LOG = logging.getLogger(__name__)


class InfobloxObjectManipulator(object):
    FIELDS = ['ttl', 'use_ttl']

    def __init__(self, connector):
        self.connector = connector

    def get_member(self, member_name, return_fields=None, extattrs=None):
        obj = {'host_name': member_name}
        return self.connector.get_object(
            'member', obj, return_fields, extattrs
        )

    def create_member(self, name=None, platform='VNIOS',
                      mgmt=None, lan1={}, lan2=None,
                      nat_ip=None):
        member_data = {'host_name': name, 'platform': platform}
        extra_data = {}

        if lan1.get('ipv4', None):
            extra_data['vip_setting'] = lan1['ipv4']
        if lan1.get('ipv6', None):
            extra_data['ipv6_setting'] = lan1['ipv6']
        if nat_ip:
            extra_data['nat_setting'] = {
                'enabled': True,
                'external_virtual_ip': nat_ip
            }

        if mgmt and mgmt.get('ipv4', None):
            extra_data['node_info'] = [{"mgmt_network_setting": mgmt['ipv4']}]
            extra_data['mgmt_port_setting'] = {"enabled": True}

        if lan2 and lan2.get('ipv4', None):
            extra_data['lan2_enabled'] = True
            extra_data['lan2_port_setting'] = {
                'enabled': True,
                'network_setting': lan2['ipv4']
            }

        return self._create_infoblox_object('member', member_data, extra_data)

    def pre_provision_member(self, member_name,
                             hwmodel=None, hwtype='IB-VNIOS',
                             licenses=None):
        if licenses is None:
            licenses = []
        extra_data = {'pre_provisioning': {
            'hardware_info': [{'hwmodel': hwmodel, 'hwtype': hwtype}],
            'licenses': licenses}
        }
        self._update_infoblox_object('member', {'host_name': member_name},
                                     extra_data)

    def configure_member_dns(self, member_name,
                             enable_dns=False):
        extra_data = {'enable_dns': enable_dns}
        self._update_infoblox_object('member:dns', {'host_name': member_name},
                                     extra_data)

    def delete_member(self, member_name):
        member_data = {'host_name': member_name}
        self._delete_infoblox_object('member', member_data)

    def create_anycast_loopback(self, member_name, ip, enable_bgp=False,
                                enable_ospf=False):
        anycast_loopback = {
            'anycast': True,
            'enable_bgp': enable_bgp,
            'enable_ospf': enable_ospf,
            'interface': 'LOOPBACK'}
        if ':' in ip:
            anycast_loopback['ipv6_network_setting'] = {
                'virtual_ip': ip}
        else:
            anycast_loopback['ipv4_network_setting'] = {
                'address': ip,
                'subnet_mask': '255.255.255.255'}

        member = self._get_infoblox_object_or_none(
            'member', {'host_name': member_name},
            return_fields=['additional_ip_list'])

        # Should we raise some exception here or just log object not found?
        if not member:
            LOG.error(_("Grid Member %(name)s is not found, can not assign "
                        "Anycast Loopback ip %(ip)s"),
                      {'name': member_name, 'ip': ip})
            return
        additional_ip_list = member['additional_ip_list'] + [anycast_loopback]

        payload = {'additional_ip_list': additional_ip_list}
        self._update_infoblox_object_by_ref(member['_ref'], payload)

    def delete_anycast_loopback(self, ip, member_name=None):
        """Delete anycast loopback ip address.

        :param ip: anycast ip address to delete from loopback interface
        :param member_name: name of grid member on which anycast ip should
                            be deleted. If member name is None, then anycast
                            address is deleted from each member where found.
        """
        members_for_update = []
        if member_name:
            member = self._get_infoblox_object_or_none(
                'member', {'host_name': member_name},
                return_fields=['additional_ip_list'])
            if member and member['additional_ip_list']:
                members_for_update.append(member)
        else:
            members_for_update = self.connector.get_object(
                'member', return_fields=['additional_ip_list'])

        for member in members_for_update:
            # update members only if address to remove is found
            update_this_member = False
            new_ip_list = []
            for iface in member['additional_ip_list']:
                ipv4 = iface.get('ipv4_network_setting')
                if ipv4 and ip in ipv4['address']:
                    update_this_member = True
                    continue
                ipv6 = iface.get('ipv6_network_setting')
                if ipv6 and ip in ipv6['virtual_ip']:
                    update_this_member = True
                    continue
                new_ip_list.append(iface)
            if update_this_member:
                payload = {'additional_ip_list': new_ip_list}
                self._update_infoblox_object_by_ref(member['_ref'], payload)

    def get_all_ns_groups(self, return_fields=None, extattrs=None):
        obj = {}
        return self.connector.get_object(
            'nsgroup', obj, return_fields, extattrs
        )

    def get_ns_group(self, group_name, return_fields=None, extattrs=None):
        obj = {'name': group_name}
        return self.connector.get_object(
            'nsgroup', obj, return_fields, extattrs
        )

    def update_ns_group(self, group_name, group):
        self._update_infoblox_object('nsgroup', {'name': group_name},
                                     group)

    def create_ospf(self, member_name, ospf_options_dict):
        """Add ospf settings to the grid member."""
        member = self._get_infoblox_object_or_none(
            'member', {'host_name': member_name},
            return_fields=['ospf_list'])

        # Should we raise some exception here or just log object not found?
        if not member:
            LOG.error(_("Grid Member %(name)s is not found"),
                      {'name': member_name})
        ospf_list = member['ospf_list'] + [ospf_options_dict]
        payload = {'ospf_list': ospf_list}
        self._update_infoblox_object_by_ref(member['_ref'], payload)

    def delete_ospf(self, area_id, member_name):
        """Delete ospf setting for particular area_id from the grid member."""
        member = self._get_infoblox_object_or_none(
            'member', {'host_name': member_name},
            return_fields=['ospf_list'])
        if member and member['ospf_list']:
            # update member only if area_id match
            update_this_member = False
            new_ospf_list = []
            for ospf_settings in member['ospf_list']:
                if str(area_id) == ospf_settings.get('area_id'):
                    update_this_member = True
                    continue
                new_ospf_list.append(ospf_settings)
            if update_this_member:
                payload = {'ospf_list': new_ospf_list}
                self._update_infoblox_object_by_ref(member['_ref'], payload)

    def create_dns_view(self, net_view_name, dns_view_name):
        dns_view_data = {'name': dns_view_name,
                         'network_view': net_view_name}
        return self._create_infoblox_object('view', dns_view_data)

    def delete_dns_view(self, net_view_name):
        net_view_data = {'name': net_view_name}
        self._delete_infoblox_object('view', net_view_data)

    def create_network_view(self, net_view_name, tenant_id):
        net_view_data = {'name': net_view_name}
        extattrs = {'extattrs': {'TenantID': {'value': tenant_id}}}
        return self._create_infoblox_object('networkview',
                                            net_view_data, extattrs)

    def delete_network_view(self, net_view_name):
        if net_view_name == 'default':
            # never delete default network view
            return

        net_view_data = {'name': net_view_name}
        self._delete_infoblox_object('networkview', net_view_data)

    def create_tsig(self, name, algorithm, secret):
        tsig = {
            'name': name,
            'key': secret
        }
        self._create_infoblox_object(
            'tsig', tsig,
            check_if_exists=True)

    def delete_tsig(self, name, algorithm, secret):
        tsig = {
            'name': name,
            'key': secret
        }
        self._delete_infoblox_object(
            'tsig', tsig,
            check_if_exists=True)

    def create_multi_tenant_dns_view(self, net_view, tenant):
        if not net_view:
            net_view = "%s.%s" % (self.connector.network_view, tenant)
        dns_view = "%s.%s" % (self.connector.dns_view, net_view)

        try:
            self.create_network_view(
                net_view_name=net_view,
                tenant_id=tenant)

            self.create_dns_view(
                net_view_name=net_view,
                dns_view_name=dns_view)
        except exc.InfobloxException as e:
            LOG.warning(_("Issue happens during views creating: %s"), e)

        LOG.debug("net_view: %s, dns_view: %s" % (net_view, dns_view))
        return dns_view

    def get_dns_view(self, tenant):
        if not self.connector.multi_tenant:
            return self.connector.dns_view
        else:
            # Look for the network view with the specified TenantID EA
            net_view = self._get_infoblox_object_or_none(
                'networkview',
                return_fields=['name'],
                extattrs={'TenantID': {'value': tenant}})
            if net_view:
                net_view = net_view['name']

            return self.create_multi_tenant_dns_view(net_view, tenant)

    def create_zone_auth(self, fqdn, dns_view):
        try:
            self._create_infoblox_object(
                'zone_auth',
                {'fqdn': fqdn, 'view': dns_view},
                {'ns_group': self.connector.ns_group,
                 'restart_if_needed': True},
                check_if_exists=True)
        except exc.InfobloxCannotCreateObject as e:
            LOG.warning(e)

    def delete_zone_auth(self, fqdn):
        self._delete_infoblox_object(
            'zone_auth', {'fqdn': fqdn})

    def _create_infoblox_object(self, obj_type, payload,
                                additional_create_kwargs=None,
                                check_if_exists=True,
                                return_fields=None):
        if additional_create_kwargs is None:
            additional_create_kwargs = {}

        ib_object = None
        if check_if_exists:
            ib_object = self._get_infoblox_object_or_none(obj_type, payload)
            if ib_object:
                LOG.info(_(
                    "Infoblox %(obj_type)s already exists: %(ib_object)s"),
                    {'obj_type': obj_type, 'ib_object': ib_object})

        if not ib_object:
            payload.update(additional_create_kwargs)
            ib_object = self.connector.create_object(obj_type, payload,
                                                     return_fields)
            LOG.info(_("Infoblox %(obj_type)s was created: %(ib_object)s"),
                     {'obj_type': obj_type, 'ib_object': ib_object})

        return ib_object

    def _get_infoblox_object_or_none(self, obj_type, payload=None,
                                     return_fields=None, extattrs=None):
        ib_object = self.connector.get_object(obj_type, payload, return_fields,
                                              extattrs=extattrs)
        if ib_object:
            if return_fields:
                return ib_object[0]
            else:
                return ib_object[0]['_ref']

        return None

    def _update_infoblox_object(self, obj_type, payload, update_kwargs):
        ib_object_ref = None
        warn_msg = _('Infoblox %(obj_type)s will not be updated because'
                     ' it cannot be found: %(payload)s')
        try:
            ib_object_ref = self._get_infoblox_object_or_none(obj_type,
                                                              payload)
            if not ib_object_ref:
                LOG.warning(warn_msg % {'obj_type': obj_type,
                                        'payload': payload})
        except exc.InfobloxSearchError as e:
            LOG.warning(warn_msg, {'obj_type': obj_type, 'payload': payload})
            LOG.info(e)

        if ib_object_ref:
            self._update_infoblox_object_by_ref(ib_object_ref, update_kwargs)

    def _update_infoblox_object_by_ref(self, ref, update_kwargs):
        self.connector.update_object(ref, update_kwargs)
        LOG.info(_('Infoblox object was updated: %s'), ref)

    def _delete_infoblox_object(self, obj_type, payload):
        ib_object_ref = None
        warn_msg = _('Infoblox %(obj_type)s will not be deleted because'
                     ' it cannot be found: %(payload)s')
        try:
            ib_object_ref = self._get_infoblox_object_or_none(obj_type,
                                                              payload)
            if not ib_object_ref:
                LOG.warning(warn_msg, obj_type, payload)
        except exc.InfobloxSearchError as e:
            LOG.warning(warn_msg, {'obj_type': obj_type, 'payload': payload})
            LOG.info(e)

        if ib_object_ref:
            self.connector.delete_object(ib_object_ref)
            LOG.info(_('Infoblox object was deleted: %s'), ib_object_ref)
