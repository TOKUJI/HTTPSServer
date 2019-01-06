import typing
from enum import Enum, auto
from io import BytesIO
from hpack import Encoder, Decoder

# private programs
from .logger import get_logger_set
logger, log = get_logger_set('frame')


class FrameTypes(Enum):
    DATA = b'\x00'
    HEADERS = b'\x01'
    PRIORITY = b'\x02'
    RST_STREAM = b'\x03'
    SETTINGS = b'\x04'
    PUSH_PROMISE = b'\x05'
    PING = b'\x06'
    GOAWAY = b'\x07'
    WINDOW_UPDATE = b'\x08'
    COTINUATION = b'\x09'


class FrameBase(object):
    """docstring for FrameBase"""
    factory = None

    def __init__(self, length: int, type_, flags: int, stream_identifier: int):
        self.length = length
        self.type_ = type_
        self.flags = flags
        self.stream_identifier = stream_identifier
        logger.debug('type={}, '.format(self.type_) +\
                     'flag={}, '.format(self.flags) +\
                     'stream_identifier={} '.format(self.stream_identifier) +\
                     'and payload size={}'.format(self.length))


    @classmethod
    def get_factory(cls):
        if not cls.factory:
            cls.factory = {klass.FrameType().value: klass for klass in cls.__subclasses__()}
        return cls.factory

    @classmethod
    def create(cls, type_, flags, stream_identifier, data=None):
        factory = cls.get_factory()
        if not data:
            length = 0
        else:
            length = len(data)
        logger.info('length of the data is {}'.format(length))
        return factory[type_](length, type_, flags, stream_identifier, data)

    @classmethod
    def load(cls, data):
        factory = cls.get_factory()

        length = int.from_bytes(data[:3], 'big', signed=False)
        type_ = data[3:4]
        flags = int.from_bytes(data[4:5], 'big', signed=False)
        stream_identifier = int.from_bytes(data[5:9], 'big', signed=False)
        payload = data[9:]
        return factory[type_](length, type_, flags, stream_identifier, payload)

    def save(self):
        res = b''
        res += self.length.to_bytes(3, 'big', signed=False)
        res += self.type_
        res += self.flags.to_bytes(1, 'big', signed=False)
        res += self.stream_identifier.to_bytes(4, 'big', signed=False)

        return res

    @staticmethod
    def FrameType():
        raise NotImplementedException('A subclass of FrameBase should implement FrameType() method')


class SettingFrame(FrameBase):
    """docstring for SettingFrame"""
    initial_window_size = None
    def __init__(self, length: int, type_, flags: int, stream_identifier: int, data=None):
        super(SettingFrame, self).__init__(length, type_, flags, stream_identifier)
        logger.debug('SettingFrame is called.')

        self.params = {b'\x00\x01': self.set_header_table_size,
                       b'\x00\x02': self.set_enable_push,
                       b'\x00\x03': self.set_max_concurrent_streams,
                       b'\x00\x04': self.set_initial_window_size,
                       b'\x00\x05': self.set_max_frame_size,
                       }

        payload = BytesIO(data)
        while True:
            identifier = payload.read(2)
            if len(identifier) != 2:
                break

            value = payload.read(4)
            if len(value) != 4:
                break
            try:
                self.params[identifier](value)
            except KeyError:
                logger.error('unknown identifier: {}, {}'.format(identifier,
                    int.from_bytes(value, 'big', signed=False)))

    def set_header_table_size(self, value):
        self.header_table_size = int.from_bytes(value, 'big', signed=False)
        logger.debug('header_table_size: {}'.format(self.header_table_size))

    def set_enable_push(self, value):
        self.enable_push = int.from_bytes(value, 'big', signed=False)
        logger.debug('enable_push: {}'.format(self.enable_push))

    def set_initial_window_size(self, value):
        self.initial_window_size = int.from_bytes(value, 'big', signed=False)
        logger.debug('initial_window_size: {}'.format(self.initial_window_size))

    def set_max_concurrent_streams(self, value):
        self.max_concurrent_streams = int.from_bytes(value, 'big', signed=False)
        logger.debug('max_concurrent_streams: {}'.format(self.max_concurrent_streams))

    def set_max_frame_size(self, value):
        self.max_frame_size = int.from_bytes(value, 'big', signed=False)
        logger.debug('max_frame_size: {}'.format(self.max_frame_size))

    def save(self):
        base = super().save()
        # TODO: enable to alter settings parameters
        return base

    @staticmethod
    def FrameType():
        return FrameTypes.SETTINGS


class WindowUpdate(FrameBase):
    """docstring for WindowUpdate"""
    def __init__(self, length: int, type_, flags: bytes, stream_identifier: int, data=None):
        super(WindowUpdate, self).__init__(length, type_, flags, stream_identifier)
        logger.debug('WindowUpdate is called.')

        payload = BytesIO(data)
        self.set_window_size(data)

    def set_window_size(self, value):
        self.window_size = int.from_bytes(value, 'big', signed=False)
        logger.debug('window_size: {}'.format(self.window_size))
        
    def save(self):
        base = super(WindowUpdate, self).save()
        # TODO: enable to alter settings parameters
        return base

    @staticmethod
    def FrameType():
        return FrameTypes.WINDOW_UPDATE

class HeadersFlags(Enum):
    END_STREAM = 0x1
    END_HEADERS = 0x4
    PADDED = 0x8
    PRIORITY = 0x20


class Headers(FrameBase, dict):

    def __init__(self, length: int, type_, flags: bytes, stream_identifier: int, data=None):
        super(Headers, self).__init__(length, type_, flags, stream_identifier)
        logger.debug('Headers is called.')
        self.end_stream = HeadersFlags.END_STREAM.value & self.flags
        self.end_headers = HeadersFlags.END_HEADERS.value & self.flags
        self.padded = HeadersFlags.PADDED.value & self.flags
        self.priority = HeadersFlags.PRIORITY.value & self.flags
        logger.debug('{}, {}, {}, {}'.format(self.end_stream,
                                             self.end_headers,
                                             self.padded,
                                             self.priority))

        payload = BytesIO(data)

        if self.padded:
            payload.read(1)

        if self.priority: # TODO: handle priority properly
            self.stream_dependency = int.from_bytes(payload.read(4), 'big', signed=False)
            self.priority_weight = int.from_bytes(payload.read(1), 'big', signed=False)
            logger.debug('stream_dependency: {}, '.format(self.stream_dependency) +\
                         'priority_weight: {}'.format(self.priority_weight))

        if length:
            decoder = Decoder()
            fields = decoder.decode(payload.read())
            for k, v in fields:
                self[k] = v
                logger.debug('{}: {}'.format(k, v))

    def save(self):

        encoder = Encoder()
        payload = encoder.encode(self)
        self.length = len(payload)

        decoder = Decoder()
        check = decoder.decode(payload)
        logger.info('payload of the header is {}'.format(check))

        base = super().save()
        return base + payload

    @staticmethod
    def FrameType():
        return FrameTypes.HEADERS


class GoAway(FrameBase):
    def __init__(self, length: int, type_, flags: int, stream_identifier: int, data=None):
        super().__init__(length, type_, flags, stream_identifier)
        logger.debug('GoAway is called.')

        payload = BytesIO(data)
        self.stream_identifier = int.from_bytes(payload.read(4), 'big', signed=False)
        self.error_code = int.from_bytes(payload.read(4), 'big', signed=False)
        self.append_data = payload.read()
        logger.debug('stream_identifier: {}'.format(self.stream_identifier))
        logger.debug('error_code: {}'.format(self.error_code))
        logger.debug('append_data: {}'.format(self.append_data))

    @staticmethod
    def FrameType():
        return FrameTypes.GOAWAY

class RstStream(FrameBase):
    def __init__(self, length: int, type_, flags: int, stream_identifier: int, data=None):
        super().__init__(length, type_, flags, stream_identifier)
        logger.debug('RstStream is called.')
        if len(data) != 4:
            raise Exception('Frame size error')

        self.error_code = int.from_bytes(data, 'big', signed=False)
        logger.debug('error_code: {}'.format(self.error_code))

    @staticmethod
    def FrameType():
        return FrameTypes.RST_STREAM



class DataFlags(Enum):
    END_STREAM = 0x1
    PADDED = 0x8

class Data(FrameBase):
    """docstring for Data"""
    def __init__(self, length: int, type_, flags: int, stream_identifier: int, data=None):
        super().__init__(length, type_, flags, stream_identifier)
        logger.debug('Data is called.')
        self.end_stream = DataFlags.END_STREAM.value & self.flags
        self.padded = DataFlags.PADDED.value & self.flags

        payload = BytesIO(data)

        if self.padded:
            pad_length = int.from_bytes(payload.read(1), 'big', signed=False)
            # TODO: add checking logic of pad_length.
            data_length = length - pad_length - 1
        else:
            data_length = length

        self.data = payload.read(data_length)

    def save(self):
        base = super().save()
        logger.info(base)
        logger.info('payload size of the data is {}'.format(len(self.data)))
        logger.info(self.data)
        return base + self.data

    @staticmethod
    def FrameType():
        return FrameTypes.DATA


class Priority(FrameBase):
    def __init__(self, length: int, type_, flags: int, stream_identifier: int, data=None):
        super().__init__(length, type_, flags, stream_identifier)
        logger.debug('Priority is called.')

        payload = BytesIO(data)

        self.dependent_stream = int.from_bytes(payload.read(4), 'big', signed=False)
        self.weight = int.from_bytes(payload.read(1), 'big', signed=False)

    def save(self):
        base = super().save()

        payload = self.dependent_stream.to_bytes(4, 'big', signed=False) +\
               self.weight.to_bytes(1, 'big', signed=False)
        self.length = 5

        return base + payload

    @staticmethod
    def FrameType():
        return FrameTypes.PRIORITY
        


class Stream(object):
    def __init__(self, parent, weight, window_size=None):
        self.parent = parent
        self.weight = weight
        if window_size:
            self.window_size = window_size

    def __setattr__(self, key, value):
        pass
